"""
Chat route - handles conversation with the LLM orchestrator.

TODO:
- [ ] Implement LLM client (Anthropic API or local model)
- [ ] Tool dispatch (plot generation, differential, material lookup)
- [ ] Session/conversation state management
- [ ] Prompt caching for system prompt + material DB
"""

from fastapi import APIRouter, UploadFile, File
from typing import Optional

router = APIRouter()


@router.post("/chat")
async def chat(
    message: str,
    files: Optional[list[UploadFile]] = File(None),
):
    """
    Main chat endpoint.

    Accepts a user message and optional .pxt file uploads.
    Returns LLM response with optional inline plots.
    """
    # TODO: Implement
    # 1. Parse message + files
    # 2. Send to LLM with tool definitions
    # 3. Execute any tool calls (plot, differential, lookup)
    # 4. Return response with images/data
    return {"response": "ChatARPES is not yet implemented.", "plots": []}
