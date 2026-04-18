"""
ChatARPES backend (FastAPI) package.

This file runs before any submodule in `app.*` is imported. We use it to
ensure the repo root is on `sys.path` so that `from analysis.* import …`
works regardless of where the server is launched from (the repo root or
`backend/`). Keeping this in one place avoids the drift risk of each
route file performing its own path surgery.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
