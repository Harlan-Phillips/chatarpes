"""User uploads — ad-hoc files the user attaches to a chat turn.

Stored in Tigris so they survive Fly machine restarts. The agent only
sees them when the chat request lists them in `selected_uploads`.
"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.storage import (
    StorageNotConfigured,
    StoredObject,
    UPLOADS_PREFIX,
    delete as storage_delete,
    list_objects,
    put,
)

router = APIRouter(prefix="/uploads", tags=["uploads"])

MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB


class _ObjectOut(BaseModel):
    name: str
    size: int
    last_modified: str

    @classmethod
    def from_stored(cls, obj: StoredObject) -> "_ObjectOut":
        return cls(name=obj.name, size=obj.size, last_modified=obj.last_modified)


class _ListResponse(BaseModel):
    files: list[_ObjectOut]


class _UploadResponse(BaseModel):
    uploaded: list[_ObjectOut]
    skipped: list[dict]


@router.get("", response_model=_ListResponse)
def list_uploads() -> _ListResponse:
    return _ListResponse(files=[_ObjectOut.from_stored(o) for o in list_objects(UPLOADS_PREFIX)])


@router.post("", response_model=_UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_files(files: list[UploadFile] = File(...)) -> _UploadResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    uploaded: list[_ObjectOut] = []
    skipped: list[dict] = []
    for upload in files:
        name = upload.filename or "unnamed"
        data = await upload.read()
        if len(data) > MAX_FILE_SIZE_BYTES:
            skipped.append({"name": name, "reason": f"exceeds {MAX_FILE_SIZE_BYTES} bytes"})
            continue
        if "/" in name or ".." in name:
            skipped.append({"name": name, "reason": "invalid filename"})
            continue
        try:
            stored = put(UPLOADS_PREFIX, name, data, content_type=upload.content_type)
            uploaded.append(_ObjectOut.from_stored(stored))
        except StorageNotConfigured as e:
            raise HTTPException(status_code=503, detail=str(e))
    return _UploadResponse(uploaded=uploaded, skipped=skipped)


@router.delete("/{name:path}", status_code=status.HTTP_204_NO_CONTENT)
def delete_upload(name: str) -> None:
    if "/" in name or ".." in name:
        raise HTTPException(status_code=400, detail="Invalid filename")
    try:
        storage_delete(UPLOADS_PREFIX, name)
    except StorageNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
