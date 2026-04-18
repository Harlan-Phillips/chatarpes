"""
TR-ARPES API routes.

Endpoints:
    GET  /trarpes/scans              — list available scan_NNN.pxt files
    POST /trarpes/upload             — upload a .pxt (and optional .txt sidecar)
    POST /trarpes/compute            — JSON arrays for the interactive widget
    POST /trarpes/export             — PNG (publication quality)
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

# Repo-root path surgery happens once in `app/__init__.py`, so plain
# `from analysis...` works here regardless of the CWD.
from analysis.trarpes import (
    check_trarpes_compat_cached,
    compute_panels,
    discover_scans,
    load_scan,
    render_png,
)
from app.config import MAX_UPLOAD_SIZE_MB, TRARPES_DATA_DIR

router = APIRouter(prefix="/trarpes", tags=["trarpes"])

_SCAN_FILENAME_RE = re.compile(r"^scan_(\d{3})(\.pxt|\.txt)$")


# ─── schemas ───────────────────────────────────────────────────────────────────


class ComputeRequest(BaseModel):
    scan_a: int
    scan_b: int
    smoothing: float = 1.5


class ExportRequest(BaseModel):
    scan_a: int
    scan_b: int
    smoothing: float = 1.5
    diff_scale_pct: float = 95.0
    show_edc: bool = False
    edc_phi: float = 0.0


# ─── helpers ───────────────────────────────────────────────────────────────────


def _data_dir() -> Path:
    p = Path(TRARPES_DATA_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p


# ─── endpoints ─────────────────────────────────────────────────────────────────


@router.get("/scans")
def list_scans(check_compat: bool = False):
    """List available static 2D scans in the configured data directory.

    Set `check_compat=true` to include a `compat` field for each scan
    (cached by file mtime; first call for a given file is slower as it
    has to parse the Igor binary).
    """
    data_dir = _data_dir()
    entries = discover_scans(data_dir)
    scans = []
    for e in entries:
        item = e.to_dict()
        if check_compat:
            item["compat"] = check_trarpes_compat_cached(data_dir / e.filename)
        scans.append(item)
    return {"data_dir": str(data_dir), "scans": scans}


@router.post("/upload")
async def upload_scan(
    pxt: UploadFile = File(...),
    txt: Optional[UploadFile] = File(None),
):
    """Upload a .pxt file (and optional sidecar .txt).

    Filename must match `scan_NNN.pxt` or `scan_NNN.txt`.
    """
    if not pxt.filename.endswith(".pxt"):
        raise HTTPException(400, "File must be a .pxt")
    m = _SCAN_FILENAME_RE.match(pxt.filename)
    if not m:
        raise HTTPException(
            400, "Filename must be scan_NNN.pxt (e.g. scan_031.pxt)"
        )

    data_dir = _data_dir()
    target = data_dir / pxt.filename

    max_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    content = await pxt.read()
    if len(content) > max_bytes:
        raise HTTPException(413, f"File exceeds {MAX_UPLOAD_SIZE_MB} MB")
    target.write_bytes(content)

    if txt is not None and txt.filename:
        if not txt.filename.endswith(".txt"):
            raise HTTPException(400, "Sidecar must be a .txt")
        (data_dir / txt.filename).write_bytes(await txt.read())

    compat = check_trarpes_compat_cached(target)
    return {
        "ok": True,
        "scan_num": int(m.group(1)),
        "filename": pxt.filename,
        "compat": compat,
    }


@router.post("/compute")
def compute(req: ComputeRequest):
    """Compute panels for the interactive widget.

    Returns downsampled arrays suitable for JSON transport plus metadata
    (vmax, abs_diff_sorted) so the client can redraw the diff panel's
    contrast locally.
    """
    data_dir = _data_dir()
    try:
        ds_a = load_scan(req.scan_a, data_dir)
        ds_b = load_scan(req.scan_b, data_dir)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Failed to load scan: {e}")

    try:
        panels = compute_panels(ds_a, ds_b, req.smoothing)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Failed to compute panels: {e}")

    panels["scan_a"] = req.scan_a
    panels["scan_b"] = req.scan_b
    return panels


@router.post("/export")
def export_png(req: ExportRequest):
    """Render the full-resolution publication PNG."""
    data_dir = _data_dir()
    try:
        ds_a = load_scan(req.scan_a, data_dir)
        ds_b = load_scan(req.scan_b, data_dir)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Failed to load scan: {e}")

    try:
        png = render_png(
            ds_a,
            ds_b,
            scan_a_num=req.scan_a,
            scan_b_num=req.scan_b,
            smoothing=req.smoothing,
            diff_scale_pct=req.diff_scale_pct,
            show_edc=req.show_edc,
            edc_phi=req.edc_phi,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Failed to render PNG: {e}")

    filename = f"trarpes_scan_{req.scan_a:03d}_vs_{req.scan_b:03d}.png"
    return Response(
        content=png,
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
