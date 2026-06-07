"""Extract structured metadata from a data-log file using Haiku.

Called once at upload time. Stores a small JSON document the chat
endpoint can dump into the system prompt so the agent can decide which
files (if any) to read with the `read_datalog` tool. This means the
model's context stays tiny on each chat turn even with hundreds of logs.
"""

from __future__ import annotations

import json
import os
from typing import Optional

import anthropic

from app.attachments import file_to_content_blocks

INDEX_MODEL = os.getenv("INDEX_MODEL", "claude-haiku-4-5-20251001")

_SYSTEM_PROMPT = """You are extracting structured metadata from an ARPES lab data log.

Look at the file contents below and return ONLY a JSON object with these fields:
- material: string or null. The primary sample material (e.g. "TTS2", "Bi2Se3", "graphene"). Null if unidentifiable.
- date: string or null. Measurement date in YYYY-MM-DD format if found. Null if not present.
- sample_names: list of strings. All sample IDs mentioned.
- scan_types: list of strings. Types of scans recorded (e.g. "EDC", "2D map", "TR-ARPES", "card", "Fermi surface").
- summary: string. One-paragraph plain-English summary of what this file contains.
- key_terms: list of strings. 5-10 search keywords useful for retrieval (physical phenomena, instrument settings, dates, sample IDs).

Return ONLY the JSON object. No prose, no markdown code fences."""


def index_file(filename: str, data: bytes, *, max_retries: int = 1) -> dict:
    """Return a metadata dict for one data-log file.

    On any failure (network, decode, malformed JSON) returns a stub with
    `indexed=False` so callers can still surface the file in the UI.
    The chat endpoint will then attach the full file contents on demand
    via the `read_datalog` tool.
    """
    blocks = file_to_content_blocks(filename, data)
    if not blocks:
        return _stub(filename, "no content blocks")

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    user_content = blocks + [{
        "type": "text",
        "text": f"Filename: {filename}\n\nReturn the JSON metadata object now.",
    }]

    last_error: Optional[str] = None
    for _attempt in range(max_retries + 1):
        try:
            resp = client.messages.create(
                model=INDEX_MODEL,
                max_tokens=1024,
                system=_SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": user_content},
                    # Prefill forces a JSON-object response and saves a few tokens.
                    {"role": "assistant", "content": "{"},
                ],
            )
            text_parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
            raw = "{" + "".join(text_parts).strip()
            # Strip any accidental code fence
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
            meta = json.loads(raw)
            return _normalize(filename, meta)
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            last_error = f"{type(e).__name__}: {e}"
        except json.JSONDecodeError as e:
            last_error = f"json decode: {e}"
        except Exception as e:  # noqa: BLE001 — we want this to always return *something*
            last_error = f"{type(e).__name__}: {e}"

    return _stub(filename, last_error or "unknown error")


def _normalize(filename: str, meta: dict) -> dict:
    """Coerce all fields to expected types so the chat path can trust them."""
    return {
        "filename": filename,
        "indexed": True,
        "material": _as_str_or_none(meta.get("material")),
        "date": _as_str_or_none(meta.get("date")),
        "sample_names": _as_str_list(meta.get("sample_names")),
        "scan_types": _as_str_list(meta.get("scan_types")),
        "summary": _as_str_or_none(meta.get("summary")) or "",
        "key_terms": _as_str_list(meta.get("key_terms")),
    }


def _stub(filename: str, error: str) -> dict:
    return {
        "filename": filename,
        "indexed": False,
        "material": None,
        "date": None,
        "sample_names": [],
        "scan_types": [],
        "summary": "(metadata extraction failed — agent should read the file directly if relevant)",
        "key_terms": [],
        "error": error,
    }


def _as_str_or_none(v) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _as_str_list(v) -> list[str]:
    if not v:
        return []
    if isinstance(v, str):
        return [v.strip()] if v.strip() else []
    return [str(x).strip() for x in v if str(x).strip()]
