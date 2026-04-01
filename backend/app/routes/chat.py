"""
Chat route - streams responses with extended thinking using Vercel AI SDK data stream protocol.
"""

import base64
import json
import os
from pathlib import Path
from urllib.parse import quote

import anthropic
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, StreamingResponse

router = APIRouter()

PAPERS_DIR = Path(__file__).resolve().parents[3] / "knowledge" / "papers"
_paper_cache: dict[str, str] = {}


def _get_paper_names() -> list[str]:
    """Return list of PDF filenames in knowledge/papers/."""
    return [p.name for p in sorted(PAPERS_DIR.glob("*.pdf"))]


def _load_paper_blocks() -> list[dict]:
    """Load all PDFs from knowledge/papers/ as base64-encoded content blocks."""
    blocks = []
    for pdf_path in sorted(PAPERS_DIR.glob("*.pdf")):
        if pdf_path.name not in _paper_cache:
            _paper_cache[pdf_path.name] = base64.standard_b64encode(
                pdf_path.read_bytes()
            ).decode("utf-8")
        blocks.append({
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": _paper_cache[pdf_path.name],
            },
            "cache_control": {"type": "ephemeral"},
        })
    return blocks


def _build_system_prompt() -> str:
    paper_names = _get_paper_names()
    papers_list = "\n".join(f"  - {name}" for name in paper_names)

    return f"""You are ChatARPES, an AI assistant for ARPES (Angle-Resolved Photoemission Spectroscopy) researchers in the Harmony Lab.

You have been provided with the lab's TR-ARPES setup paper. Use it to answer questions accurately about the experimental setup, techniques, and capabilities.

Important note: The lab has since upgraded to a 1030nm Carbide laser. If the paper references a different laser system, mention this upgrade when relevant.

Be precise and cite specific details from the paper when answering. If something isn't covered in the paper, say so clearly.

## Citation format
When referencing information from the provided papers, cite them inline using this exact format:
  [Source: FILENAME, Section/Fig X]

Available papers:
{papers_list}

Example citation: [Source: Buss et al. - 2019 - A setup for extreme-ultraviolet ultrafast angle-re.pdf, Section III.A]

Always include at least one citation per factual claim from the paper. Place citations at the end of the relevant sentence or paragraph."""


@router.get("/papers/{filename:path}")
async def serve_paper(filename: str):
    """Serve a PDF from knowledge/papers/ for citation links."""
    pdf_path = PAPERS_DIR / filename
    if not pdf_path.exists() or not pdf_path.suffix == ".pdf":
        return {"error": "Paper not found"}
    return FileResponse(pdf_path, media_type="application/pdf", filename=filename)


@router.get("/papers")
async def list_papers():
    """List available papers."""
    return {"papers": _get_paper_names()}


@router.post("/chat")
async def chat(request: Request):
    """Chat endpoint - streams thinking + response in Vercel AI SDK data stream protocol."""
    body = await request.json()
    raw_messages = body.get("messages", [])

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    paper_blocks = _load_paper_blocks()

    # Build messages, attaching papers to first user turn
    messages = []
    first_user_seen = False
    for msg in raw_messages:
        if msg["role"] == "user" and not first_user_seen:
            first_user_seen = True
            messages.append({
                "role": "user",
                "content": paper_blocks + [{"type": "text", "text": msg["content"]}],
            })
        else:
            messages.append({"role": msg["role"], "content": msg["content"]})

    def generate():
        current_block_type = None

        with client.messages.stream(
            model=os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001"),
            max_tokens=16000,
            thinking={
                "type": "enabled",
                "budget_tokens": 10000,
            },
            system=_build_system_prompt(),
            messages=messages,
        ) as stream:
            for event in stream:
                if event.type == "content_block_start":
                    if event.content_block.type == "thinking":
                        current_block_type = "thinking"
                    elif event.content_block.type == "text":
                        current_block_type = "text"

                elif event.type == "content_block_delta":
                    if current_block_type == "thinking" and hasattr(event.delta, "thinking"):
                        # AI SDK data stream: reasoning = g:{json}\n
                        yield f'g:{json.dumps({"text": event.delta.thinking})}\n'
                    elif current_block_type == "text" and hasattr(event.delta, "text"):
                        # AI SDK data stream: text = 0:{json}\n
                        yield f"0:{json.dumps(event.delta.text)}\n"

                elif event.type == "content_block_stop":
                    current_block_type = None

            # Finish step
            response = stream.get_final_message()
            usage = {
                "promptTokens": response.usage.input_tokens,
                "completionTokens": response.usage.output_tokens,
            }
            yield f'd:{json.dumps({"finishReason": "stop", "usage": usage})}\n'

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")
