"""
File upload route - handles .pxt file uploads.

TODO:
- [ ] Validate .pxt file format
- [ ] Extract metadata from headers
- [ ] Store in session-scoped temp directory
- [ ] Return metadata preview to user
"""

from fastapi import APIRouter, UploadFile, File

router = APIRouter()


@router.post("/upload")
async def upload_pxt(files: list[UploadFile] = File(...)):
    """
    Upload one or more .pxt files.

    Returns extracted metadata for each file.
    """
    # TODO: Implement
    # 1. Save uploaded files to temp storage
    # 2. Load via analysis engine to validate format
    # 3. Extract metadata (delay stage, temperature, etc.)
    # 4. Return metadata summary
    return {"uploaded": [f.filename for f in files], "metadata": []}
