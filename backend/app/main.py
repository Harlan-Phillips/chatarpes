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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.chat import router as chat_router
from app.routes.trarpes import router as trarpes_router

app = FastAPI(
    title="ChatARPES",
    description="AI assistant for ARPES researchers",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(trarpes_router)


@app.get("/health")
def health():
    return {"status": "ok"}
