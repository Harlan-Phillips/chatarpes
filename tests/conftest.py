"""
Shared pytest configuration.

Responsibilities:
    1. Put repo root and `backend/` on sys.path so `analysis.*` and `app.*`
       imports work regardless of where pytest is invoked from.
    2. Stub the `igor2` module so `analysis.parsers.kaindl_pxt` can be
       imported in environments where igor2 isn't installed. Tests that
       exercise the real igor2 loader will either install it or patch
       `igor` themselves.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_BACKEND = _REPO_ROOT / "backend"

for p in (_REPO_ROOT, _BACKEND):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)


# ─── igor2 stub ────────────────────────────────────────────────────────────────
# Only install the stub if the real thing isn't importable, so users with
# igor2 installed still test against the real library for any call they
# don't explicitly patch.
def _install_igor_stub() -> None:
    """Fallback stub for when igor2 isn't installed.

    The real kaindl_pxt loader lazy-imports ``igor2.packed`` and
    ``igor2.record.wave.WaveRecord`` from inside functions, so the
    module itself can be imported even without igor2. The stub only
    exists so tests that patch the ``_packed_load`` / ``_is_wave_record``
    helpers can still import igor2 as a sanity check if they want to.
    """
    try:
        import igor2  # noqa: F401  (real package present)
        return
    except ImportError:
        pass

    igor2 = types.ModuleType("igor2")
    packed = types.ModuleType("igor2.packed")
    record = types.ModuleType("igor2.record")
    wave_mod = types.ModuleType("igor2.record.wave")

    class _FakeWaveRecord:
        def __init__(self, wave):
            self.wave = wave

    def _fake_load(path, initial_byte_order="="):
        raise NotImplementedError(
            "igor2 stub — tests that hit the loader must patch "
            "analysis.parsers.kaindl_pxt._packed_load / _is_wave_record."
        )

    packed.load = _fake_load
    wave_mod.WaveRecord = _FakeWaveRecord
    record.wave = wave_mod
    igor2.packed = packed
    igor2.record = record

    sys.modules["igor2"] = igor2
    sys.modules["igor2.packed"] = packed
    sys.modules["igor2.record"] = record
    sys.modules["igor2.record.wave"] = wave_mod


_install_igor_stub()
