"""
ChatARPES Backend - FastAPI Orchestrator

Routes LLM requests, dispatches analysis tools, manages sessions.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="ChatARPES",
    description="AI assistant for ARPES researchers",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict to frontend domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


# TODO: Add routes
# - POST /chat          -> LLM conversation endpoint
# - POST /upload        -> .pxt file upload
# - GET  /materials     -> material database lookup
# - GET  /session/{id}  -> session state
