"""Vercel serverless entry for the CuraVar FastAPI backend.

Vercel routes /api/* to this file. We mount the real FastAPI app (web/api/main.py)
under /api so its clean routes (/classify, /triage, ...) match the browser's
same-origin /api/* calls. The curavar engine is imported by web/api/service.py,
which adds the repo-root curavar/ package to sys.path itself.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi import FastAPI
from web.api.main import app as _inner

app = FastAPI()
app.mount("/api", _inner)
