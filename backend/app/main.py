"""
ChatARPES Backend - FastAPI Orchestrator
"""

from pathlib import Path

from dotenv import load_dotenv

# Load .env from the repo root regardless of CWD so `uvicorn app.main:app`
# works whether launched from `backend/` or from the repo root. Use
# override=True so that an empty/stale value inherited from the parent
# shell (e.g. `ANTHROPIC_API_KEY=""`) doesn't silently win over the
# real key in .env.
_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / ".env", override=True)
load_dotenv(override=True)  # also try CWD, harmless if missing

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.routes.chat import router as chat_router
from app.routes.trarpes import router as trarpes_router

# Comma-separated list of allowed origins. Defaults to localhost dev URLs.
# In production set ALLOWED_ORIGINS to your frontend's deployed origin(s),
# e.g. "https://chatarpes.pages.dev,https://chatarpes.example.com".
_origins_env = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")
ALLOWED_ORIGINS = [o.strip() for o in _origins_env.split(",") if o.strip()]

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

app = FastAPI(
    title="ChatARPES",
    description="AI assistant for ARPES researchers",
    version="0.1.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(trarpes_router)


@app.get("/health")
def health():
    return {"status": "ok"}
