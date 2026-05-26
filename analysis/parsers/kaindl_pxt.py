"""
Minimal Kaindl-endstation .pxt reader.

Distilled from the pyarpes package
(https://github.com/chstan/arpes ; files arpes/load_pxt.py and
arpes/endstations/plugin/kaindl.py) without the heavy framework.

pyarpes depended on chstan's unmaintained `igor` fork whose top-level
API (``igor.igorpy.load()`` returning a container with ``.children``) no
longer exists in modern `igor2`. We use ``igor2.packed.load()`` directly
— it returns ``(records, filesystem)`` where wave records expose a dict
with ``wData``, ``wave_header``, and ``note``.

Dependencies: numpy, xarray, igor2 (``pip install igor2``).

Semantics note:
    ``arpes.io.load_data(path, location="Kaindl")`` runs
    ``SESEndstation.load_single_frame``, which calls
    ``repair.negate_energy(read_single_pxt(frame_path))``. The lab's
    reference notebook then does ``ds.assign_coords(eV=ds.eV.values * -1)``
    on top of that — effectively undoing the negation. To match the
    notebook's computed values, we default ``negate_energy=False`` here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Union

import numpy as np
import xarray as xr


# Igor dim unit -> xarray dim name, mirroring arpes.load_pxt.wave_to_xarray.
_UNIT_TO_DIM = {
    "eV": "eV",
    "deg": "phi",
    "Pwr Supply V": "volts",
    "K2200 V": "volts",
}

# Header key renames, mirroring arpes.load_pxt.read_header.
_HEADER_RENAME = {
    "sample_x": "x",
    "sample_y_(vert)": "y",
    "sample_y": "y",
    "sample_z": "z",
    "bl_energy": "hv",
}


# ─── igor2 indirection (lazy + test-patchable) ────────────────────────────────
# Kept as module attributes so tests can monkeypatch them without having
# the real igor2 installed. The server can also start even if igor2 is
# missing — we only raise when someone actually tries to load a .pxt,
# and when that happens we surface a clear dependency message (not a
# generic `IOError` from further down the decode path) so the TR-ARPES
# routes can report it intelligibly.


class Pxt2DependencyError(RuntimeError):
    """Raised when the real `igor2` package is needed but unavailable."""


_IGOR2_HINT = (
    "igor2 is required to load .pxt files. Install with `pip install igor2`."
)


def _packed_load(path, initial_byte_order):
    """Thin wrapper around `igor2.packed.load()` with a clear ImportError message."""
    try:
        from igor2 import packed
    except ImportError as exc:  # pragma: no cover - exercised via explicit test
        raise Pxt2DependencyError(_IGOR2_HINT) from exc
    return packed.load(path, initial_byte_order=initial_byte_order)


def _is_wave_record(obj) -> bool:
    try:
        from igor2.record.wave import WaveRecord
    except ImportError as exc:
        raise Pxt2DependencyError(_IGOR2_HINT) from exc
    return isinstance(obj, WaveRecord)


# ─── helpers ───────────────────────────────────────────────────────────────────


def _safe_decode(b: Any, prefer: str | None = None) -> str:
    """Tolerant bytes->str, matching arpes.utilities.string.safe_decode."""
    if isinstance(b, str):
        return b
    if not isinstance(b, (bytes, bytearray)):
        return str(b)
    codecs = ["utf-8", "latin-1", "ascii"]
    if prefer:
        codecs = [prefer] + codecs
    for c in codecs:
        try:
            return b.decode(c)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", errors="replace")


def _parse_notes(raw) -> dict:
    """Parse Igor wave `notes` bytes into a header dict."""
    if raw is None:
        return {}
    text = _safe_decode(raw).replace("\r", "\n")
    out: dict = {}
    for line in text.split("\n"):
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip().lower().replace(" ", "_")
        v = v.strip()
        try:
            v = int(v)
        except ValueError:
            try:
                v = float(v)
            except ValueError:
                pass
        out[k] = v
    for src, dst in _HEADER_RENAME.items():
        if src in out:
            out[dst] = out.pop(src)
    return out


def _wave_dict_to_xarray(wave_obj) -> xr.DataArray:
    """Convert an igor2 ``load()``-style wave dict to an xarray.DataArray.

    The input is either:
      * the ``.wave`` attribute of ``igor2.record.wave.WaveRecord``
        (a dict with ``{"version": int, "wave": {...}}``), or
      * the inner ``wave`` dict directly.
    Both forms appear depending on the igor2 code path.
    """
    # Normalize to the inner dict that has wData / wave_header / note.
    if isinstance(wave_obj, dict) and "wave" in wave_obj and isinstance(wave_obj["wave"], dict):
        inner = wave_obj["wave"]
    else:
        inner = wave_obj

    data = np.asarray(inner["wData"])
    header = inner.get("wave_header", {})
    n_dim = list(header.get("nDim", [])) or list(data.shape)
    sfA = list(header.get("sfA", []))
    sfB = list(header.get("sfB", []))
    # Igor stores up to 4 dims; trim to ones with nDim > 0.
    active = [i for i, n in enumerate(n_dim) if n and i < data.ndim]
    # Fallback: if header reports 0 dims but data is multi-dim, use data shape.
    if not active:
        active = list(range(data.ndim))
        n_dim = list(data.shape)
        sfA = [1.0] * data.ndim
        sfB = [0.0] * data.ndim

    # Per-dim unit strings. igor2's packed WaveRecord typically stores the
    # authoritative dim units inside ``wave_header["dimUnits"]`` as a 2D
    # ndarray of single-byte chars (dtype='|S1'), shape (4, 4). The
    # ``inner["dimension_units"]`` field is usually just ``b""``. Prefer
    # whichever source actually has content.
    def _collect_unit(entry) -> str:
        """Decode a single per-dim unit entry."""
        if entry is None:
            return ""
        if isinstance(entry, (bytes, bytearray)):
            return _safe_decode(entry).strip("\x00 \t\r\n")
        if isinstance(entry, str):
            return entry.strip("\x00 \t\r\n")
        # Array-of-single-bytes or list-of-bytes (numpy |S1 rows, or lists)
        try:
            parts = []
            for b in entry:
                if b is None or b == b"" or b == "":
                    continue
                if isinstance(b, (bytes, bytearray)):
                    parts.append(b)
                else:
                    parts.append(str(b).encode())
            return _safe_decode(b"".join(parts)).strip("\x00 \t\r\n")
        except TypeError:
            return _safe_decode(entry).strip("\x00 \t\r\n")

    def _read_dim_units(n_active: int) -> list[str]:
        """Try every known field for per-dim units; keep the first non-empty result."""
        sources = (
            inner.get("dimension_units"),
            header.get("dimUnits"),
        )
        for src in sources:
            if src is None:
                continue
            # Skip sentinels: `b""`, empty list/array, scalar strings with no content.
            try:
                if isinstance(src, (bytes, bytearray, str)) and not src:
                    continue
                if hasattr(src, "__len__") and len(src) == 0:
                    continue
            except TypeError:
                pass
            units: list[str] = []
            for i in range(n_active):
                try:
                    units.append(_collect_unit(src[i]))
                except (IndexError, TypeError):
                    units.append("")
            if any(units):
                return units
        return [""] * n_active

    unit_strs = _read_dim_units(len(active))

    # Build dim names, applying the eV/deg->phi rename and filling unknowns.
    extras = iter(["W", "X", "Y", "Z"])
    dims: list[str] = []
    for u in unit_strs:
        if u and u in _UNIT_TO_DIM:
            dims.append(_UNIT_TO_DIM[u])
        elif u:
            dims.append(u)
        else:
            dims.append(next(extras))

    # Build coordinate arrays from sfA / sfB.
    coords = {}
    for di, src_idx in enumerate(active):
        n = int(n_dim[src_idx]) if src_idx < len(n_dim) else data.shape[di]
        step = float(sfA[src_idx]) if src_idx < len(sfA) else 1.0
        off = float(sfB[src_idx]) if src_idx < len(sfB) else 0.0
        coords[dims[di]] = off + step * np.arange(n)

    # Byteswap non-native dtypes so downstream numpy ops don't complain.
    if data.dtype.byteorder not in ("=", "|"):
        data = data.byteswap().view(data.dtype.newbyteorder())

    # Trim data to the active dims (igor may include trailing 0-sized dims).
    if data.ndim > len(active):
        slicer = tuple(slice(None) if i in active else 0 for i in range(data.ndim))
        data = data[slicer]

    return xr.DataArray(
        data,
        coords=coords,
        dims=dims,
        attrs=_parse_notes(inner.get("note", b"")),
    )


# ─── public loader ─────────────────────────────────────────────────────────────


def load_kaindl_pxt(
    path: Union[str, Path],
    *,
    negate_energy: bool = False,
) -> xr.Dataset:
    """Load a single Kaindl/SES .pxt file to an xarray.Dataset.

    Parameters
    ----------
    path : str | Path
        Path to the .pxt file.
    negate_energy : bool, default False
        If True, flip the sign of the eV axis (matches pyarpes's
        ``SESEndstation.load_single_frame`` behavior). The lab notebook
        flips it a second time after loading, so ``False`` here keeps
        the same numeric values the notebook was computing with.

    Returns
    -------
    xr.Dataset with a single data variable ``"spectrum"`` and
    coordinates (``eV``, ``phi``) plus any scalar coords from the
    Kaindl ``postprocess_final`` step.
    """
    path = str(Path(path).absolute())

    records = None
    last_err: Exception | None = None
    for order in ("=", ">", "<"):
        try:
            result = _packed_load(path, initial_byte_order=order)
            # igor2.packed.load returns (records, filesystem)
            records = result[0] if isinstance(result, tuple) else result
            break
        except Pxt2DependencyError:
            # Dependency errors aren't a byte-order issue — propagate so
            # callers see a clear "install igor2" message instead of the
            # generic "could not decode" fallback below.
            raise
        except Exception as e:  # noqa: BLE001 - byte-order probe
            last_err = e
            continue
    if records is None:
        raise IOError(f"Could not decode Igor file: {path} (last error: {last_err})")

    waves: list = []
    for rec in records:
        if _is_wave_record(rec):
            wave = getattr(rec, "wave", None)
            if wave is not None:
                waves.append(wave)
    if not waves:
        raise ValueError(f"No Igor waves found in {path}")

    # Pick the largest wave (the actual spectrum) in case there are
    # small auxiliary waves in the same packed file.
    def _size(w):
        inner = w["wave"] if "wave" in w else w
        return int(np.asarray(inner["wData"]).size)

    wave = max(waves, key=_size)
    da = _wave_dict_to_xarray(wave)

    # Kaindl RENAME_KEYS — only "Delay Stage" -> "delay" is relevant.
    if "Delay Stage" in da.attrs:
        da.attrs["delay"] = da.attrs.pop("Delay Stage")

    if negate_energy and "eV" in da.coords:
        da = da.assign_coords(eV=-da.eV.values)

    # Kaindl ``postprocess_final`` deg -> rad for angular coords.
    for c in ("theta", "beta", "phi"):
        if c in da.dims:
            da = da.assign_coords({c: da.coords[c].values * np.pi / 180.0})
    for k in ("theta", "beta", "alpha", "chi"):
        if k in da.attrs:
            try:
                da.attrs[k] = float(da.attrs[k]) * np.pi / 180.0
            except (TypeError, ValueError):
                pass

    ds = xr.Dataset({"spectrum": da}, attrs=dict(da.attrs))
    return ds


def read_scan_info(txt_path: Union[str, Path]) -> str:
    """Best-effort sidecar .txt parser matching the reference notebook.

    Returns the region name (or comments, if present) as a short label,
    or "" if the file can't be read or has neither field.
    """
    p = Path(txt_path)
    if not p.exists():
        return ""
    try:
        with open(p, "r", errors="ignore") as f:
            txt = f.read()
    except OSError:
        return ""

    comments = ""
    for line in txt.split("\n"):
        if "Region Name" in line and "=" in line:
            return line.split("=", 1)[1].strip()
        if "Comments" in line and "=" in line:
            c = line.split("=", 1)[1].strip()
            if c:
                comments = c
    return comments
