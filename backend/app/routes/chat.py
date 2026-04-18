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

from app.tools.tool_definitions import ANTHROPIC_TOOLS

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

Always include at least one citation per factual claim from the paper. Place citations at the end of the relevant sentence or paragraph.

## Interactive TR-ARPES tool
When the user wants to compare two TR-ARPES scans, compute a pump-probe differential,
explore scan_NNN.pxt data, "open the TR-ARPES analysis", or when the user's message
contains a bracketed hint like `[TR-ARPES tool selected by user. Uploaded scans: ...]`
— invoke the `trarpes_open` tool. The frontend will render an interactive widget inline.

If the hint lists specific scan numbers (e.g. `scan_030, scan_031`), pass the first as
`scan_a` and the second as `scan_b`. If the hint says "no scans attached yet", call the
tool with no arguments.

**Emit a short explanation BEFORE the tool call**, in the same assistant turn, covering:
  1. What analysis you're setting up (e.g. "A = reference, B = pumped; B − A is the
     pump-induced change") and, if the user named specific scan numbers, why those
     choices make sense.
  2. How to read the differential colormap: **red** = intensity increased after pumping
     (electrons excited into previously-unoccupied states), **blue** = intensity decreased
     (depopulation), **white** = no change.
  3. 2–3 concrete physical signatures to look for that match the material or context the
     user mentioned — e.g. CDW gap collapse (blue below the gap, red above it), hot
     electron tails above E_F, coherent phonon oscillations for closely-spaced delays.
     If you don't know the material, describe the generic TR-ARPES signatures briefly.
  4. Practical tips: suggest enabling the EDC comparison at a specific phi if relevant,
     or adjusting smoothing if the differential looks noisy.

Keep the explanation to ~4-8 sentences. Do NOT describe the widget's UI itself —
describe the physics and what the user should watch for in the plots.

If the user named specific scan numbers, pass them as scan_a (reference) and scan_b
(pumped); otherwise call the tool with no arguments so the user can upload / pick in
the widget."""


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
        tool_name: str | None = None
        tool_args_buf = ""

        with client.messages.stream(
            model=os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001"),
            max_tokens=16000,
            thinking={
                "type": "enabled",
                "budget_tokens": 10000,
            },
            tools=ANTHROPIC_TOOLS,
            system=_build_system_prompt(),
            messages=messages,
        ) as stream:
            for event in stream:
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "thinking":
                        current_block_type = "thinking"
                    elif block.type == "text":
                        current_block_type = "text"
                    elif block.type == "tool_use":
                        current_block_type = "tool_use"
                        tool_name = block.name
                        tool_args_buf = ""

                elif event.type == "content_block_delta":
                    if current_block_type == "thinking" and hasattr(event.delta, "thinking"):
                        # AI SDK data stream: reasoning = g:{json}\n
                        yield f'g:{json.dumps({"text": event.delta.thinking})}\n'
                    elif current_block_type == "text" and hasattr(event.delta, "text"):
                        # AI SDK data stream: text = 0:{json}\n
                        yield f"0:{json.dumps(event.delta.text)}\n"
                    elif current_block_type == "tool_use" and hasattr(event.delta, "partial_json"):
                        # Accumulate — tool args stream as a JSON fragment
                        tool_args_buf += event.delta.partial_json

                elif event.type == "content_block_stop":
                    if current_block_type == "tool_use" and tool_name:
                        try:
                            args = json.loads(tool_args_buf) if tool_args_buf else {}
                        except json.JSONDecodeError:
                            args = {}
                        # Custom frame: 9:{toolName, args}
                        yield f'9:{json.dumps({"toolName": tool_name, "args": args})}\n'
                        tool_name = None
                        tool_args_buf = ""
                    current_block_type = None

            # Finish step
            response = stream.get_final_message()
            usage = {
                "promptTokens": response.usage.input_tokens,
                "completionTokens": response.usage.output_tokens,
            }
            yield f'd:{json.dumps({"finishReason": "stop", "usage": usage})}\n'

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")
