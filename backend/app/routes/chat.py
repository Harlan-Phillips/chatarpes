from __future__ import annotations

"""Chat route — streams thinking + responses with a tool-execution loop.

Architecture
------------
The model sees a lightweight *index* of every data log (filename plus
extracted metadata: material, date, samples, summary, keywords). When
the user's question touches a specific file, the model calls the
`read_datalog` tool; the server executes it against Tigris and feeds
the contents back as a tool_result. This keeps each chat payload small
no matter how many data logs the lab has.

Client-side tools (currently just `trarpes_open`) are still surfaced to
the frontend as `9:` frames — the UI renders a widget and the model
doesn't need a server-side result.

Stream protocol (Vercel AI SDK data stream):
    g:{"text": ...}             reasoning/thinking delta
    0:"text"                    assistant text delta
    9:{toolName, args}          client-side tool invocation
    3:"error message"           error
    d:{finishReason, usage}     final frame (one per request, at the end)
"""

import base64
import json
import os
from pathlib import Path

import anthropic
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, StreamingResponse

from app.attachments import file_to_content_blocks
from app.storage import (
    DATALOGS_PREFIX,
    UPLOADS_PREFIX,
    get as storage_get,
    list_objects,
)
from app.tools.tool_definitions import ANTHROPIC_TOOLS

router = APIRouter()

PAPERS_DIR = Path(__file__).resolve().parents[3] / "knowledge" / "papers"
_paper_cache: dict[str, str] = {}

# Tools whose results we resolve server-side and feed back into the
# conversation. Anything not listed here is treated as a client-side
# tool — emitted to the frontend as a 9: frame and given a stub
# tool_result so the API doesn't complain about an orphan tool_use.
SERVER_TOOLS = {"list_datalogs", "read_datalog"}

# Hard ceiling on the tool-execution loop to prevent runaway costs.
MAX_TOOL_ITERATIONS = 5

META_SUFFIX = ".meta.json"


# ─── reference docs ────────────────────────────────────────────────────────────


def _get_paper_names() -> list[str]:
    return [p.name for p in sorted(PAPERS_DIR.glob("*.pdf"))]


def _load_paper_blocks() -> list[dict]:
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


# ─── data-log index ────────────────────────────────────────────────────────────


def _load_datalog_index() -> list[dict]:
    """Return the metadata index for every uploaded data log.

    Skips the `.meta.json` sidecars themselves. Files without metadata
    yet (e.g. uploaded before the indexer existed) get a minimal stub.
    """
    entries: list[dict] = []
    for obj in list_objects(DATALOGS_PREFIX):
        if obj.name.endswith(META_SUFFIX):
            continue
        meta_name = obj.name + META_SUFFIX
        try:
            raw = storage_get(DATALOGS_PREFIX, meta_name)
            entries.append(json.loads(raw))
        except FileNotFoundError:
            entries.append({
                "filename": obj.name,
                "indexed": False,
                "summary": "(no metadata yet — call read_datalog directly if needed)",
            })
        except json.JSONDecodeError:
            entries.append({
                "filename": obj.name,
                "indexed": False,
                "summary": "(metadata corrupt — call read_datalog directly if needed)",
            })
    return entries


def _read_datalog(name: str) -> list[dict]:
    """Tool implementation for `read_datalog`."""
    if not name or "/" in name or ".." in name or name.endswith(META_SUFFIX):
        return [{"type": "text", "text": f"Invalid data log name: {name!r}"}]
    try:
        data = storage_get(DATALOGS_PREFIX, name)
    except FileNotFoundError:
        return [{"type": "text", "text": f"Data log not found: {name}"}]
    return file_to_content_blocks(name, data)


def _execute_server_tool(name: str, args: dict) -> list[dict]:
    """Run a server-side tool and return tool_result content blocks."""
    if name == "list_datalogs":
        return [{
            "type": "text",
            "text": json.dumps({"data_logs": _load_datalog_index()}, ensure_ascii=False),
        }]
    if name == "read_datalog":
        return _read_datalog(args.get("name", ""))
    return [{"type": "text", "text": f"Unknown server tool: {name}"}]


# ─── user uploads (still inline-attach, per design) ────────────────────────────


def _load_selected_upload_blocks(names: list[str]) -> list[dict]:
    blocks: list[dict] = []
    for name in names:
        if not name or "/" in name or ".." in name:
            continue
        try:
            data = storage_get(UPLOADS_PREFIX, name)
        except FileNotFoundError:
            continue
        blocks.extend(file_to_content_blocks(name, data))
    return blocks


# ─── prompt ────────────────────────────────────────────────────────────────────


def _format_index_for_prompt(entries: list[dict]) -> str:
    if not entries:
        return "(no data logs uploaded yet)"
    lines: list[str] = []
    for e in entries:
        parts = [f"- **{e.get('filename')}**"]
        if e.get("material"):
            parts.append(f"material={e['material']}")
        if e.get("date"):
            parts.append(f"date={e['date']}")
        if e.get("sample_names"):
            parts.append(f"samples={','.join(e['sample_names'])}")
        if e.get("scan_types"):
            parts.append(f"scans={','.join(e['scan_types'])}")
        header = "  ".join(parts)
        summary = (e.get("summary") or "").strip()
        keywords = e.get("key_terms") or []
        sub = f"    {summary}"
        if keywords:
            sub += f"  (keywords: {', '.join(keywords)})"
        lines.append(header)
        lines.append(sub)
    return "\n".join(lines)


def _build_system_prompt() -> str:
    paper_names = _get_paper_names()
    papers_list = "\n".join(f"  - {name}" for name in paper_names)
    datalog_index_text = _format_index_for_prompt(_load_datalog_index())

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

## Lab data logs (retrieved on demand)
The lab's data logs are indexed below. You do NOT see the raw file contents up front — only this lightweight index. When a user question is about a specific experiment, sample, date, or measurement, decide which one or two files are most relevant, then call the `read_datalog` tool with the exact filename to fetch the contents. Prefer reading the smallest possible set — every read costs tokens.

If the user asks broadly about what data exists, you can answer directly from the index without calling any tool.

Data-log index:
{datalog_index_text}

## Interactive TR-ARPES tool
When the user wants to compare two TR-ARPES scans, compute a pump-probe differential,
explore scan_NNN.pxt data, "open the TR-ARPES analysis", or when the user's message
contains a bracketed hint like `[TR-ARPES tool selected by user. Uploaded scans: ...]`
— invoke the `trarpes_open` tool. The frontend will render an interactive widget inline.

If the hint lists specific scan numbers (e.g. `scan_030, scan_031`), pass the first as
`scan_a` and the second as `scan_b`. If the hint says "no scans attached yet", call the
tool with no arguments.

**Emit a short explanation BEFORE the tool call**, in the same assistant turn, covering:
  1. What analysis you're setting up.
  2. How to read the differential colormap: **red** = intensity increased, **blue** = depopulation, **white** = no change.
  3. 2–3 concrete physical signatures to look for in this material/context.
  4. Practical tips (EDC at specific phi, smoothing, etc.).

Keep the explanation to ~4-8 sentences. Do NOT describe the widget UI itself."""


# ─── PDF passthrough for citations ─────────────────────────────────────────────


@router.get("/papers/{filename:path}")
async def serve_paper(filename: str):
    pdf_path = PAPERS_DIR / filename
    if not pdf_path.exists() or pdf_path.suffix != ".pdf":
        return {"error": "Paper not found"}
    return FileResponse(pdf_path, media_type="application/pdf", filename=filename)


@router.get("/papers")
async def list_papers():
    return {"papers": _get_paper_names()}


# ─── chat ──────────────────────────────────────────────────────────────────────


def _stream_error_frame(msg: str) -> str:
    return f"3:{json.dumps(msg)}\n"


def _done_frame(reason: str, usage: dict) -> str:
    return f"d:{json.dumps({'finishReason': reason, 'usage': usage})}\n"


def _serialize_content_block(block) -> dict:
    """Convert an Anthropic SDK content block to a dict the API will accept
    when we echo the assistant message back in a follow-up turn."""
    if hasattr(block, "model_dump"):
        return block.model_dump(exclude_none=True)
    # Fallback for older SDKs.
    return dict(block.__dict__)


@router.post("/chat")
async def chat(request: Request):
    body = await request.json()
    raw_messages = body.get("messages", [])
    selected_uploads: list[str] = body.get("selected_uploads", []) or []

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    paper_blocks = _load_paper_blocks()
    upload_blocks = _load_selected_upload_blocks(selected_uploads)

    # Papers ride the first user turn so they cache. User uploads ride
    # the most recent user turn. Data logs are NOT auto-attached — the
    # agent fetches them on demand via read_datalog.
    last_user_idx = max(
        (i for i, m in enumerate(raw_messages) if m["role"] == "user"),
        default=-1,
    )

    messages: list[dict] = []
    first_user_seen = False
    for i, msg in enumerate(raw_messages):
        if msg["role"] == "user":
            content: list[dict] = []
            if not first_user_seen:
                first_user_seen = True
                content.extend(paper_blocks)
            if i == last_user_idx and upload_blocks:
                content.extend(upload_blocks)
            content.append({"type": "text", "text": msg["content"]})
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": msg["role"], "content": msg["content"]})

    system_prompt = _build_system_prompt()
    model = os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001")

    def generate():
        total_usage = {"promptTokens": 0, "completionTokens": 0}

        for iteration in range(MAX_TOOL_ITERATIONS):
            current_block_type: str | None = None
            tool_name_buf: str | None = None
            tool_args_buf = ""

            try:
                with client.messages.stream(
                    model=model,
                    max_tokens=16000,
                    thinking={"type": "enabled", "budget_tokens": 10000},
                    tools=ANTHROPIC_TOOLS,
                    system=system_prompt,
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
                                tool_name_buf = block.name
                                tool_args_buf = ""

                        elif event.type == "content_block_delta":
                            if current_block_type == "thinking" and hasattr(event.delta, "thinking"):
                                yield f'g:{json.dumps({"text": event.delta.thinking})}\n'
                            elif current_block_type == "text" and hasattr(event.delta, "text"):
                                yield f"0:{json.dumps(event.delta.text)}\n"
                            elif current_block_type == "tool_use" and hasattr(event.delta, "partial_json"):
                                tool_args_buf += event.delta.partial_json

                        elif event.type == "content_block_stop":
                            # Only emit client-side tools to the frontend.
                            # Server-side tool calls are handled below.
                            if (
                                current_block_type == "tool_use"
                                and tool_name_buf
                                and tool_name_buf not in SERVER_TOOLS
                            ):
                                try:
                                    args = json.loads(tool_args_buf) if tool_args_buf else {}
                                except json.JSONDecodeError:
                                    args = {}
                                yield f'9:{json.dumps({"toolName": tool_name_buf, "args": args})}\n'
                            tool_name_buf = None
                            tool_args_buf = ""
                            current_block_type = None

                    final_message = stream.get_final_message()

            except anthropic.APIStatusError as e:
                detail = getattr(e, "message", None) or str(e)
                yield _stream_error_frame(f"Anthropic API error ({e.status_code}): {detail}")
                yield _done_frame("error", total_usage)
                return
            except Exception as e:  # noqa: BLE001
                yield _stream_error_frame(
                    f"Chat request failed: {type(e).__name__}: {e}. "
                    f"Often caused by oversized attachments — try smaller user uploads."
                )
                yield _done_frame("error", total_usage)
                return

            total_usage["promptTokens"] += final_message.usage.input_tokens
            total_usage["completionTokens"] += final_message.usage.output_tokens

            # Collect tool_use blocks from this turn. The real Anthropic
            # SDK always exposes `.content`, but tests may mock a final
            # message without it — in that case there's nothing to
            # execute server-side, so we exit cleanly.
            final_content = getattr(final_message, "content", None) or []
            tool_uses = [
                b for b in final_content
                if getattr(b, "type", None) == "tool_use"
            ]
            server_calls = [t for t in tool_uses if t.name in SERVER_TOOLS]

            if not server_calls:
                # No tools to execute server-side — we're done. Client
                # tools (e.g. trarpes_open) already got their 9: frame.
                yield _done_frame("stop", total_usage)
                return

            # Echo the assistant turn so the next stream() has the full
            # context (thinking blocks included — required when extended
            # thinking is on).
            messages.append({
                "role": "assistant",
                "content": [_serialize_content_block(b) for b in final_content],
            })

            # Build tool_result blocks. We must provide one for EVERY
            # tool_use in the assistant turn, even client-side ones,
            # otherwise the next API call errors out.
            tool_results: list[dict] = []
            for tu in tool_uses:
                tool_id = tu.id
                args = tu.input if isinstance(tu.input, dict) else {}
                if tu.name in SERVER_TOOLS:
                    # Status nudge for the user — appears inline in the
                    # assistant message before the continuation streams in.
                    if tu.name == "read_datalog":
                        target = args.get("name", "data log")
                        status_msg = f"\n\n_Reading `{target}`..._\n\n"
                        yield f"0:{json.dumps(status_msg)}\n"
                    elif tu.name == "list_datalogs":
                        status_msg = "\n\n_Consulting data-log index..._\n\n"
                        yield f"0:{json.dumps(status_msg)}\n"
                    result_content = _execute_server_tool(tu.name, args)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": result_content,
                    })
                else:
                    # Client tool: stub result so the API is happy.
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": [{"type": "text", "text": "[Tool surfaced in UI]"}],
                    })

            messages.append({"role": "user", "content": tool_results})
            # Loop continues with a fresh stream() call.

        # Hit the iteration cap.
        yield _stream_error_frame(
            f"Stopping after {MAX_TOOL_ITERATIONS} tool-use iterations to prevent runaway."
        )
        yield _done_frame("error", total_usage)

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")
