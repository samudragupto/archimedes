"""ARCHIMEDES API + worker package.

Two processes share this package:
  * the FastAPI server (app.main:app) — auth, uploads, job launching, export
  * the worker (worker/main.py) — runs the LangGraph pipeline as a Nebius
    Serverless Job or a local subprocess
"""
