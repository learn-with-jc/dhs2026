# setup.py
from setuptools import setup, find_packages

setup(
    name         = "prism",
    version      = "1.0.0",
    description  = "PRism: Enterprise Compliance AI — DataHack Summit 2026",
    author       = "Jatin Chaudhary",
    packages     = find_packages(exclude=["tests*", "notebooks*", "app*"]),
    python_requires = ">=3.11",
    install_requires = [],   # see requirements.txt
)