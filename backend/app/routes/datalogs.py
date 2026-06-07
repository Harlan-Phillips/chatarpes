"""Data logs — persistent reference docs (Excel logs, instruction manuals).

Each upload triggers an indexing pass that extracts material/date/sample
metadata via a one-shot Haiku call. Only the lightweight index lands in
the chat system prompt; the model fetches full file contents on demand
via the `read_datalog` tool. This keeps chat payloads tiny no matter
how many logs the lab has accumulated.
"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.indexing import index_file
from app.storage import (
    DATALOGS_PREFIX,
    StorageNotConfigured,
    StoredObject,
    delete as storage_delete,
    get as storage_get,
    list_objects,
    put,
)

router = APIRouter(prefix="/datalogs", tags=["datalogs"])

MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB
META_SUFFIX = ".meta.json"


def _is_meta(name: str) -> bool:
    return name.endswith(META_SUFFIX)


def _meta_key(filename: str) -> str:
    return filename + META_SUFFIX


# ─── schemas ───────────────────────────────────────────────────────────────────


class _ObjectOut(BaseModel):
    name: str
    size: int
    last_modified: str

    @classmethod
    def from_stored(cls, obj: StoredObject) -> "_ObjectOut":
        return cls(name=obj.name, size=obj.size, last_modified=obj.last_modified)


class _IndexEntry(BaseModel):
    filename: str
    indexed: bool
    material: Optional[str] = None
    date: Optional[str] = None
    sample_names: list[str] = []
    scan_types: list[str] = []
    summary: str = ""
    key_terms: list[str] = []
    error: Optional[str] = None


class _ListResponse(BaseModel):
    files: list[_ObjectOut]


class _IndexResponse(BaseModel):
    entries: list[_IndexEntry]


class _UploadResponse(BaseModel):
    uploaded: list[_IndexEntry]
    skipped: list[dict]


# ─── helpers ───────────────────────────────────────────────────────────────────


def _read_meta(filename: str) -> _IndexEntry:
    """Load the metadata sidecar for one data log, or return a stub if absent."""
    try:
        raw = storage_get(DATALOGS_PREFIX, _meta_key(filename))
        return _IndexEntry(**json.loads(raw))
    except FileNotFoundError:
        return _IndexEntry(
            filename=filename,
            indexed=False,
            summary="(no metadata — file uploaded before indexing existed, or indexing is still running)",
        )
    except (json.JSONDecodeError, Exception):  # noqa: BLE001
        return _IndexEntry(
            filename=filename,
            indexed=False,
            summary="(metadata file corrupt — reindex or re-upload)",
        )


def _write_meta(filename: str, meta: dict) -> None:
    payload = json.dumps(meta, ensure_ascii=False).encode("utf-8")
    put(DATALOGS_PREFIX, _meta_key(filename), payload, content_type="application/json")


def _list_files_only() -> list[StoredObject]:
    return [o for o in list_objects(DATALOGS_PREFIX) if not _is_meta(o.name)]


# ─── routes ────────────────────────────────────────────────────────────────────


@router.get("", response_model=_ListResponse)
def list_datalogs() -> _ListResponse:
    """Bare file list — names and sizes, no metadata."""
    return _ListResponse(files=[_ObjectOut.from_stored(o) for o in _list_files_only()])


@router.get("/index", response_model=_IndexResponse)
def get_index() -> _IndexResponse:
    """Full index: every data log with its extracted metadata."""
    return _IndexResponse(
        entries=[_read_meta(o.name) for o in _list_files_only()]
    )


@router.post("", response_model=_UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_datalogs(files: list[UploadFile] = File(...)) -> _UploadResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    uploaded: list[_IndexEntry] = []
    skipped: list[dict] = []
    for upload in files:
        name = upload.filename or "unnamed"
        data = await upload.read()
        if len(data) > MAX_FILE_SIZE_BYTES:
            skipped.append({"name": name, "reason": f"exceeds {MAX_FILE_SIZE_BYTES} bytes"})
            continue
        if "/" in name or ".." in name or _is_meta(name):
            skipped.append({"name": name, "reason": "invalid filename"})
            continue
        try:
            put(DATALOGS_PREFIX, name, data, content_type=upload.content_type)
        except StorageNotConfigured as e:
            raise HTTPException(status_code=503, detail=str(e))

        # Index the file. Failures don't block the upload — the metadata
        # stub still gets written so the chat path can surface the file.
        meta = index_file(name, data)
        try:
            _write_meta(name, meta)
        except StorageNotConfigured:
            pass  # storage already raised above; unreachable
        uploaded.append(_IndexEntry(**meta))

    return _UploadResponse(uploaded=uploaded, skipped=skipped)


@router.post("/{name:path}/reindex", response_model=_IndexEntry)
def reindex(name: str) -> _IndexEntry:
    """Re-run the indexer on an existing file (e.g. after a transient failure)."""
    if "/" in name or ".." in name or _is_meta(name):
        raise HTTPException(status_code=400, detail="Invalid filename")
    try:
        data = storage_get(DATALOGS_PREFIX, name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"{name} not found")
    except StorageNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    meta = index_file(name, data)
    _write_meta(name, meta)
    return _IndexEntry(**meta)


@router.delete("/{name:path}", status_code=status.HTTP_204_NO_CONTENT)
def delete_datalog(name: str) -> None:
    if "/" in name or ".." in name or _is_meta(name):
        raise HTTPException(status_code=400, detail="Invalid filename")
    try:
        storage_delete(DATALOGS_PREFIX, name)
        # Sidecar may not exist — delete is idempotent.
        storage_delete(DATALOGS_PREFIX, _meta_key(name))
    except StorageNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
