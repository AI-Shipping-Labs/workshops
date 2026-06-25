"""
Vercel serverless entrypoint.

Vercel turns files under `api/` into Functions and, for Python, serves any module
that exposes an ASGI `app`. We just put the `backend/` package on the path and
re-export the FastAPI app, so the same code runs locally (uvicorn) and on Vercel.

`vercel.json` rewrites only the API routes (/chat, /search, /health) here; the
static frontend is served by Vercel's CDN from `frontend/out`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from main import app  # noqa: E402  (re-exported for Vercel to discover)

__all__ = ["app"]
