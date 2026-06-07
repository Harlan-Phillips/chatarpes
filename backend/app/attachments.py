"""Convert stored file bytes into Anthropic API content blocks.

PDFs go in as `document` blocks with base64 data. Text-like files (txt,
md, csv) are decoded as plain text. Spreadsheets (xlsx, xls) are parsed
to a markdown-ish table representation so the model sees structured data
without needing a tool call. Unknown types fall back to a short notice
so the model knows the file exists but couldn't be inlined.
"""

from __future__ import annotations

import base64
import io
import os
from pathlib import Path
from typing import Optional

SUPPORTED_TEXT_EXTS = {".txt", ".md", ".csv", ".tsv", ".log", ".json", ".yaml", ".yml"}
SUPPORTED_EXCEL_EXTS = {".xlsx", ".xlsm", ".xls"}
SUPPORTED_PDF_EXTS = {".pdf"}

# Hard cap per file when inlining text. Keeps a single oversized log
# from blowing the context window.
MAX_TEXT_CHARS = 200_000


def _excel_to_text(data: bytes, filename: str) -> str:
    """Render an .xlsx as one markdown-ish table per sheet."""
    try:
        import pandas as pd
    except ImportError:
        return f"[{filename}: Excel parsing unavailable on server (pandas not installed)]"

    try:
        sheets = pd.read_excel(io.BytesIO(data), sheet_name=None, dtype=str)
    except Exception as e:
        return f"[{filename}: failed to parse as Excel: {e}]"

    parts: list[str] = [f"# {filename}"]
    for sheet_name, df in sheets.items():
        df = df.fillna("")
        parts.append(f"\n## Sheet: {sheet_name}\n")
        # Markdown-ish table; keep it compact.
        if df.empty:
            parts.append("(empty)")
            continue
        cols = list(df.columns)
        parts.append("| " + " | ".join(str(c) for c in cols) + " |")
        parts.append("|" + "|".join(["---"] * len(cols)) + "|")
        for _, row in df.iterrows():
            parts.append("| " + " | ".join(str(v) for v in row) + " |")
    text = "\n".join(parts)
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + f"\n\n[truncated — full file is {len(text)} chars]"
    return text


def file_to_content_blocks(filename: str, data: bytes) -> list[dict]:
    """Return a list of Anthropic content blocks for one stored file.

    Always returns at least one block. PDFs return a single `document`
    block; everything else returns a `text` block describing or
    containing the file.
    """
    ext = Path(filename).suffix.lower()

    if ext in SUPPORTED_PDF_EXTS:
        return [{
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": base64.standard_b64encode(data).decode("utf-8"),
            },
            "title": filename,
            "cache_control": {"type": "ephemeral"},
        }]

    if ext in SUPPORTED_EXCEL_EXTS:
        text = _excel_to_text(data, filename)
        return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]

    if ext in SUPPORTED_TEXT_EXTS:
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception as e:
            return [{"type": "text", "text": f"[{filename}: decode error: {e}]"}]
        if len(text) > MAX_TEXT_CHARS:
            text = text[:MAX_TEXT_CHARS] + f"\n\n[truncated — full file is {len(text)} chars]"
        return [{
            "type": "text",
            "text": f"# {filename}\n\n{text}",
            "cache_control": {"type": "ephemeral"},
        }]

    # Unknown — leave the model a breadcrumb.
    return [{
        "type": "text",
        "text": f"[Attached file `{filename}` ({len(data)} bytes) — type not inlined; ask the user if you need the contents]",
    }]
