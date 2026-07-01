# sentinel_x/platform/observability.py
"""
Sentinel-X | Observability Layer

Two capabilities in one module:

1. TRACING
   ─────────────────────────────────────────────────────────────────
   LangSmith (cloud) when ENABLE_LANGSMITH=true and a valid
   LANGSMITH_API_KEY is set. LangChain traces ALL chain/LLM calls
   automatically via its global tracer — no callback injection needed.

   Local SQLite fallback when LangSmith is not configured.
   Implements BaseCallbackHandler to capture the same events
   (run_id, parent_run_id, inputs, outputs, latency, token counts)
   into a local `trace_runs` table.

2. PHASE RESULT CACHE
   ─────────────────────────────────────────────────────────────────
   PhaseCache stores serialised phase outputs keyed by
   (pr_id, phase, pr_hash) in a `phase_cache` SQLite table.
   A SHA-256 digest of the PR JSON is included so the entry is
   automatically invalidated if the PR data changes.

Both share a single SQLite file: data/processed/sentinel_x.db
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "processed" / "sentinel_x.db"


# ─────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────

def _json_default(obj: Any) -> Any:
    """Custom JSON encoder: handles Pydantic models and enums."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "value"):
        return obj.value
    return str(obj)


# ─────────────────────────────────────────────────────────────────
# LOCAL SQLITE TRACER  (LangSmith fallback)
# ─────────────────────────────────────────────────────────────────

class LocalSQLiteTracer(BaseCallbackHandler):
    """
    LangChain BaseCallbackHandler that writes run events to SQLite.

    Captures the same structural data as LangSmith:
      - run_id / parent_run_id hierarchy (chain → llm nesting)
      - run_type (llm | chain | tool)
      - inputs / outputs (truncated to 400 chars)
      - latency_ms, model_name, token counts

    One row per run, updated in-place as on_*_end fires.
    """

    def __init__(self, db_path: Path = DB_PATH) -> None:
        super().__init__()
        self.db_path = db_path
        self._lock: threading.Lock = threading.Lock()
        self._start_ms: dict[str, float] = {}
        self._init_db()

    # ── connection ────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path), check_same_thread=False)

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trace_runs (
                    run_id            TEXT PRIMARY KEY,
                    parent_run_id     TEXT,
                    run_type          TEXT,
                    name              TEXT,
                    start_time        TEXT,
                    end_time          TEXT,
                    latency_ms        REAL,
                    inputs_json       TEXT,
                    outputs_json      TEXT,
                    error             TEXT,
                    model_name        TEXT,
                    prompt_tokens     INTEGER,
                    completion_tokens INTEGER,
                    tags_json         TEXT
                )
            """)
            conn.commit()

    # ── LLM events ────────────────────────────────────────────────

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        rid = str(run_id)
        self._start_ms[rid] = datetime.utcnow().timestamp() * 1000
        model = (serialized.get("kwargs") or {}).get("model", "")
        with self._lock, self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO trace_runs
                  (run_id, parent_run_id, run_type, name,
                   start_time, inputs_json, model_name, tags_json)
                VALUES (?,?,?,?,?,?,?,?)
            """, (
                rid,
                str(parent_run_id) if parent_run_id else None,
                "llm",
                serialized.get("name", "LLM"),
                datetime.utcnow().isoformat(),
                json.dumps({"prompts": [p[:300] for p in prompts[:2]]}),
                model,
                json.dumps(tags or []),
            ))
            conn.commit()

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        rid = str(run_id)
        start = self._start_ms.pop(rid, None)
        latency = (datetime.utcnow().timestamp() * 1000 - start) if start else None

        text = ""
        token_usage: dict[str, Any] = {}
        if response.generations:
            gen = response.generations[0][0]
            text = (gen.text if hasattr(gen, "text") else str(gen))[:400]
        if response.llm_output:
            token_usage = response.llm_output.get("token_usage", {})

        with self._lock, self._conn() as conn:
            conn.execute("""
                UPDATE trace_runs
                SET end_time=?, latency_ms=?, outputs_json=?,
                    prompt_tokens=?, completion_tokens=?
                WHERE run_id=?
            """, (
                datetime.utcnow().isoformat(),
                latency,
                json.dumps({"text": text}),
                token_usage.get("prompt_tokens"),
                token_usage.get("completion_tokens"),
                rid,
            ))
            conn.commit()

    def on_llm_error(
        self,
        error: Exception,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE trace_runs SET error=?, end_time=? WHERE run_id=?",
                (str(error)[:500], datetime.utcnow().isoformat(), str(run_id)),
            )
            conn.commit()

    # ── Chain events ───────────────────────────────────────────────

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any] | Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        rid = str(run_id)
        self._start_ms[rid] = datetime.utcnow().timestamp() * 1000
        if isinstance(inputs, dict):
            inp = {k: str(v)[:150] for k, v in inputs.items()}
        else:
            inp = {"value": str(inputs)[:150]}
        # Extract a human-readable name from serialized["id"] list if present
        sid = serialized.get("id")
        name = sid[-1] if isinstance(sid, list) and sid else serialized.get("name", "Chain")
        with self._lock, self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO trace_runs
                  (run_id, parent_run_id, run_type, name,
                   start_time, inputs_json, tags_json)
                VALUES (?,?,?,?,?,?,?)
            """, (
                rid,
                str(parent_run_id) if parent_run_id else None,
                "chain",
                name,
                datetime.utcnow().isoformat(),
                json.dumps(inp),
                json.dumps(tags or []),
            ))
            conn.commit()

    def on_chain_end(
        self,
        outputs: dict[str, Any] | Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        rid = str(run_id)
        start = self._start_ms.pop(rid, None)
        latency = (datetime.utcnow().timestamp() * 1000 - start) if start else None
        if isinstance(outputs, dict):
            out = {k: str(v)[:200] for k, v in outputs.items()}
        else:
            out = {"value": str(outputs)[:200]}
        with self._lock, self._conn() as conn:
            conn.execute("""
                UPDATE trace_runs
                SET end_time=?, latency_ms=?, outputs_json=?
                WHERE run_id=?
            """, (
                datetime.utcnow().isoformat(),
                latency,
                json.dumps(out),
                rid,
            ))
            conn.commit()

    def on_chain_error(
        self,
        error: Exception,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE trace_runs SET error=?, end_time=? WHERE run_id=?",
                (str(error)[:500], datetime.utcnow().isoformat(), str(run_id)),
            )
            conn.commit()


# ─────────────────────────────────────────────────────────────────
# PHASE RESULT CACHE
# ─────────────────────────────────────────────────────────────────

class PhaseCache:
    """
    SQLite-backed cache for per-phase evaluation results.

    Cache key: (pr_id, phase, pr_hash)
    pr_hash = SHA-256[:16] of the JSON-serialised PR data.
    Any change to the PR data (amount, description, attachments …)
    produces a different hash and forces a fresh evaluation.

    Serialisation contract:
      Phase 1 / 2 / 4  →  Pydantic model_dump(mode='json')
                           restored via ModelClass.model_validate(dict)
      Phase 3           →  display-relevant fields only (plain dict)
                           restored as plain dict (display code uses .get())
    """

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self._lock: threading.Lock = threading.Lock()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path), check_same_thread=False)

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS phase_cache (
                    pr_id       TEXT    NOT NULL,
                    phase       INTEGER NOT NULL,
                    pr_hash     TEXT    NOT NULL,
                    result_json TEXT    NOT NULL,
                    computed_at TEXT    NOT NULL,
                    PRIMARY KEY (pr_id, phase)
                )
            """)
            conn.commit()

    def _pr_hash(self, pr_data: dict) -> str:
        payload = json.dumps(pr_data, sort_keys=True, default=str).encode()
        return hashlib.sha256(payload).hexdigest()[:16]

    def get(self, pr_id: str, phase: int, pr_data: dict) -> dict | None:
        """Return cached result dict on hit, None on miss or hash mismatch."""
        pr_hash = self._pr_hash(pr_data)
        row = self._conn().execute(
            "SELECT result_json, computed_at FROM phase_cache "
            "WHERE pr_id=? AND phase=? AND pr_hash=?",
            (pr_id, phase, pr_hash),
        ).fetchone()
        if row:
            logger.debug(
                "Cache HIT  Phase %d | %s (computed %s)", phase, pr_id, row[1]
            )
            return json.loads(row[0])
        logger.debug("Cache MISS Phase %d | %s", phase, pr_id)
        return None

    def set(self, pr_id: str, phase: int, pr_data: dict, result: dict) -> None:
        """Persist a phase result dict."""
        pr_hash = self._pr_hash(pr_data)
        with self._lock, self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO phase_cache
                  (pr_id, phase, pr_hash, result_json, computed_at)
                VALUES (?,?,?,?,?)
            """, (
                pr_id,
                phase,
                pr_hash,
                json.dumps(result, default=_json_default),
                datetime.utcnow().isoformat(),
            ))
            conn.commit()
        logger.info("Cached Phase %d result for %s", phase, pr_id)

    def invalidate(self, pr_id: str) -> None:
        """Remove all cached phases for a PR (force re-evaluation)."""
        with self._lock, self._conn() as conn:
            conn.execute("DELETE FROM phase_cache WHERE pr_id=?", (pr_id,))
            conn.commit()
        logger.info("Cache invalidated for %s", pr_id)

    def stats(self) -> dict[str, int]:
        """Cached entry counts per phase, useful for the UI banner."""
        rows = self._conn().execute(
            "SELECT phase, COUNT(*) FROM phase_cache GROUP BY phase"
        ).fetchall()
        return {f"phase_{r[0]}": r[1] for r in rows}

    def list_cached_prs(self) -> list[dict]:
        """Return a list of cached PR entries with metadata."""
        rows = self._conn().execute(
            "SELECT pr_id, phase, computed_at FROM phase_cache ORDER BY computed_at DESC"
        ).fetchall()
        return [{"pr_id": r[0], "phase": r[1], "computed_at": r[2]} for r in rows]


# ─────────────────────────────────────────────────────────────────
# TRACING SETUP  (call once per session)
# ─────────────────────────────────────────────────────────────────

def setup_tracing() -> list[LocalSQLiteTracer]:
    """
    Configure observability for the session.

    Returns a list of callback handlers to pass into chain/graph
    `.invoke()` calls via `config={"callbacks": callbacks}`.

    LangSmith path (returns []):
      Sets LANGCHAIN_TRACING_V2 + LANGCHAIN_API_KEY env vars.
      LangChain's global tracer picks them up automatically —
      no explicit callback injection required.

    Local SQLite path (returns [LocalSQLiteTracer()]):
      LangSmith not configured → write identical events to
      data/processed/sentinel_x.db :: trace_runs table.
    """
    import os
    from config.settings import ENABLE_LANGSMITH, LANGSMITH_API_KEY, LANGSMITH_PROJECT

    if ENABLE_LANGSMITH and LANGSMITH_API_KEY and len(LANGSMITH_API_KEY) > 20:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"]    = LANGSMITH_API_KEY
        os.environ["LANGCHAIN_PROJECT"]    = LANGSMITH_PROJECT
        logger.info(
            "LangSmith tracing ENABLED → project=%s", LANGSMITH_PROJECT
        )
        return []   # automatic — no callback injection needed

    tracer = LocalSQLiteTracer()
    logger.info(
        "LangSmith not configured → local SQLite tracing at %s", tracer.db_path
    )
    return [tracer]
