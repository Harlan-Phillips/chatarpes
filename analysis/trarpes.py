"""
TR-ARPES analysis logic, ported from the lab's reference notebook.

The notebook flow:
    1. Scan DATA_DIR for `scan_NNN.pxt` (excluding `_NNN_NNN.pxt` map variants).
    2. For each, read the sibling `scan_NNN.txt` for a region/comments label.
    3. User picks two scans (A = reference, B = pumped).
    4. Compute a gaussian-smoothed difference (B - A).
    5. Optionally cut an EDC at a given phi, averaged over ±3 channels.
    6. Render three heatmaps (A, B, diff) + optional EDC line plot.

This module exposes the same pieces as pure functions so both a FastAPI
route (live interactive widget) and a PNG-export route can reuse them.
"""

from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr
from scipy.ndimage import gaussian_filter

from analysis.parsers.kaindl_pxt import load_kaindl_pxt, read_scan_info


# ─── scan discovery ────────────────────────────────────────────────────────────

_SCAN_RE = re.compile(r"^scan_(\d{3})\.pxt$")


@dataclass
class ScanEntry:
    num: int
    filename: str
    info: str  # "Region Name" or "Comments" from the sidecar .txt

    def to_dict(self) -> dict:
        return {"num": self.num, "filename": self.filename, "info": self.info}


def discover_scans(data_dir: str | Path) -> list[ScanEntry]:
    """Find static 2D scans in `data_dir`.

    Matches `scan_NNN.pxt` exactly — excludes `scan_NNN_NNN.pxt` map files.
    Returned list is sorted by scan number.
    """
    p = Path(data_dir)
    if not p.exists():
        return []
    out: list[ScanEntry] = []
    for name in os.listdir(p):
        m = _SCAN_RE.match(name)
        if not m:
            continue
        num = int(m.group(1))
        info = read_scan_info(p / f"scan_{num:03d}.txt")
        out.append(ScanEntry(num=num, filename=name, info=info))
    out.sort(key=lambda e: e.num)
    return out


# ─── caching loader ────────────────────────────────────────────────────────────

_cache: dict[tuple[str, int], xr.Dataset] = {}


def load_scan(
    scan_num: int,
    data_dir: str | Path,
    *,
    negate_energy: bool = False,
) -> xr.Dataset:
    """Load a scan with an in-memory cache (per (data_dir, num))."""
    key = (str(Path(data_dir).absolute()), scan_num)
    if key in _cache:
        return _cache[key]
    path = Path(data_dir) / f"scan_{scan_num:03d}.pxt"
    ds = load_kaindl_pxt(path, negate_energy=negate_energy)
    _cache[key] = ds
    return ds


def clear_cache() -> None:
    _cache.clear()
    _compat_cache.clear()


# ─── compatibility check ───────────────────────────────────────────────────────

# Per-file compat cache keyed by absolute path; value is (mtime, result).
_compat_cache: dict[str, tuple[float, dict]] = {}


def check_trarpes_compat(path: str | Path) -> dict:
    """Quick scan of a `.pxt` file to determine TR-ARPES compatibility.

    The lab's TR-ARPES workflow (see reference notebook) expects each scan
    to be a 2D frame with `eV` (energy) and `phi` (emission angle) axes.
    Theta/angle maps (`scan_NNN_NNN.pxt`) and 1D calibration scans fail
    here. We load through the Kaindl pipeline and inspect shape + dims.

    Returns
    -------
    dict with at least `ok: bool`. On failure, `reason: str` explains why.
    On success, also returns `shape: [int, int]` and `dims: [str, str]`.
    """
    p = Path(path)
    if not p.exists():
        return {"ok": False, "reason": f"File does not exist: {p}"}
    try:
        ds = load_kaindl_pxt(p)
    except Exception as e:  # noqa: BLE001 — any loader failure = incompatible
        return {"ok": False, "reason": f"Failed to load: {e}"}

    spec = _get_spectrum(ds)
    dims = list(spec.dims)
    shape = list(spec.shape)

    if spec.ndim != 2:
        return {
            "ok": False,
            "reason": f"Expected 2D (eV × phi) data, got {spec.ndim}D with dims {dims}",
            "dims": dims,
            "shape": shape,
        }
    if "eV" not in dims:
        return {
            "ok": False,
            "reason": f"Missing eV axis; got dims {dims}",
            "dims": dims,
            "shape": shape,
        }
    if "phi" not in dims:
        return {
            "ok": False,
            "reason": f"Missing phi axis; got dims {dims}",
            "dims": dims,
            "shape": shape,
        }
    return {"ok": True, "dims": dims, "shape": shape}


def check_trarpes_compat_cached(path: str | Path) -> dict:
    """`check_trarpes_compat` with an mtime-keyed cache."""
    p = Path(path)
    key = str(p.absolute())
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return {"ok": False, "reason": f"File not accessible: {p}"}
    cached = _compat_cache.get(key)
    if cached and cached[0] == mtime:
        return cached[1]
    result = check_trarpes_compat(p)
    _compat_cache[key] = (mtime, result)
    return result


def _get_spectrum(ds: xr.Dataset) -> xr.DataArray:
    if "spectrum" in ds.data_vars:
        return ds["spectrum"]
    return list(ds.data_vars.values())[0]


# ─── computation ───────────────────────────────────────────────────────────────


def _ensure_eV_phi(spec: xr.DataArray) -> xr.DataArray:
    """Ensure the DataArray is oriented as (eV, phi)."""
    if spec.dims[:2] == ("eV", "phi"):
        return spec
    if spec.dims[:2] == ("phi", "eV"):
        return spec.transpose("eV", "phi", *spec.dims[2:])
    # Unknown layout — best effort: leave alone
    return spec


def _downsample(arr: np.ndarray, max_size: int) -> np.ndarray:
    """Block-average `arr` so neither axis exceeds `max_size`."""
    if arr.ndim != 2:
        return arr
    h, w = arr.shape
    fy = max(1, int(np.ceil(h / max_size)))
    fx = max(1, int(np.ceil(w / max_size)))
    if fy == 1 and fx == 1:
        return arr
    new_h = (h // fy) * fy
    new_w = (w // fx) * fx
    trimmed = arr[:new_h, :new_w]
    return trimmed.reshape(new_h // fy, fy, new_w // fx, fx).mean(axis=(1, 3))


def _downsample_coord(coord: np.ndarray, target_len: int) -> np.ndarray:
    if len(coord) == target_len:
        return coord
    # Simple linear resample preserving endpoints
    idx = np.linspace(0, len(coord) - 1, target_len)
    return np.interp(idx, np.arange(len(coord)), coord)


def compute_panels(
    ds_a: xr.Dataset,
    ds_b: xr.Dataset,
    smoothing: float,
    *,
    max_size: int = 200,
) -> dict[str, Any]:
    """Produce the three panels + metadata needed for the interactive view.

    Mirrors the notebook's trim/smooth/diff logic and then downsamples for
    JSON transport. Clients use `vmax` as the upper limit for the A/B
    panels and `abs_diff_sorted` to recompute the diff contrast percentile
    without an extra round-trip.
    """
    specA = _ensure_eV_phi(_get_spectrum(ds_a))
    specB = _ensure_eV_phi(_get_spectrum(ds_b))

    dA = np.asarray(specA.values, dtype=float)
    dB = np.asarray(specB.values, dtype=float)
    eV_A = np.asarray(specA.coords["eV"].values)
    phi_A = np.asarray(specA.coords["phi"].values)

    # Record original shapes before trimming — useful for diagnostics.
    orig_shape_a = list(dA.shape)
    orig_shape_b = list(dB.shape)

    # Trim to common size — notebook behavior
    min_e = min(dA.shape[0], dB.shape[0])
    min_p = min(dA.shape[1], dB.shape[1])
    dA = dA[:min_e, :min_p]
    dB = dB[:min_e, :min_p]
    eV = eV_A[:min_e]
    phi = phi_A[:min_p]

    if smoothing and smoothing > 0:
        dA_s = gaussian_filter(dA, sigma=float(smoothing))
        dB_s = gaussian_filter(dB, sigma=float(smoothing))
    else:
        dA_s, dB_s = dA, dB

    diff = dB_s - dA_s

    # Contrast reference for A/B panels
    pos = dA_s[dA_s > 0]
    vmax = float(np.percentile(pos, 97)) if pos.size else 1.0

    # Send a downsampled histogram of |diff| so the client can recompute
    # np.percentile(|diff|, p) locally when the slider moves.
    abs_diff = np.abs(diff).ravel()
    if abs_diff.size > 2000:
        idx = np.linspace(0, abs_diff.size - 1, 2000).astype(int)
        abs_diff_sorted = np.sort(abs_diff)[idx]
    else:
        abs_diff_sorted = np.sort(abs_diff)

    # Downsample the 2D arrays for transport
    dA_out = _downsample(dA_s, max_size)
    dB_out = _downsample(dB_s, max_size)
    diff_out = _downsample(diff, max_size)
    eV_out = _downsample_coord(eV, dA_out.shape[0])
    phi_out = _downsample_coord(phi, dA_out.shape[1])

    return {
        "eV": eV_out.tolist(),
        "phi": phi_out.tolist(),
        "specA": dA_out.tolist(),
        "specB": dB_out.tolist(),
        "diff": diff_out.tolist(),
        "vmax": vmax,
        "abs_diff_sorted": abs_diff_sorted.tolist(),
        "shape_a": orig_shape_a,
        "shape_b": orig_shape_b,
    }


def compute_edc(
    spec: np.ndarray,
    phi: np.ndarray,
    phi_target: float,
    width: int = 3,
) -> tuple[np.ndarray, int]:
    """Average-over-channels EDC cut. Returns (edc, phi_index_used)."""
    phi = np.asarray(phi)
    phi_idx = int(np.argmin(np.abs(phi - phi_target)))
    lo = max(0, phi_idx - width)
    hi = min(spec.shape[1], phi_idx + width + 1)
    return spec[:, lo:hi].mean(axis=1), phi_idx


# ─── PNG export (full-resolution matplotlib) ───────────────────────────────────


def render_png(
    ds_a: xr.Dataset,
    ds_b: xr.Dataset,
    *,
    scan_a_num: int,
    scan_b_num: int,
    smoothing: float,
    diff_scale_pct: float,
    show_edc: bool,
    edc_phi: float,
    dpi: int = 300,
) -> bytes:
    """Publication-quality PNG, mirroring the notebook figure layout."""
    # Local import so server startup doesn't pay matplotlib cost unnecessarily.
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    specA = _ensure_eV_phi(_get_spectrum(ds_a))
    specB = _ensure_eV_phi(_get_spectrum(ds_b))
    dA = np.asarray(specA.values, dtype=float)
    dB = np.asarray(specB.values, dtype=float)
    eV = np.asarray(specA.coords["eV"].values)
    phi = np.asarray(specA.coords["phi"].values)

    min_e = min(dA.shape[0], dB.shape[0])
    min_p = min(dA.shape[1], dB.shape[1])
    dA = dA[:min_e, :min_p]
    dB = dB[:min_e, :min_p]
    eV = eV[:min_e]
    phi = phi[:min_p]

    if smoothing and smoothing > 0:
        dA_s = gaussian_filter(dA, sigma=float(smoothing))
        dB_s = gaussian_filter(dB, sigma=float(smoothing))
    else:
        dA_s, dB_s = dA, dB

    diff = dB_s - dA_s

    pos = dA_s[dA_s > 0]
    vmax = float(np.percentile(pos, 97)) if pos.size else 1.0
    dscale = float(np.percentile(np.abs(diff), diff_scale_pct))
    if dscale == 0:
        dscale = 1.0

    extent = [phi.min(), phi.max(), eV.min(), eV.max()]

    if show_edc:
        fig, axes = plt.subplots(1, 4, figsize=(18, 4.5))
    else:
        fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))

    axes[0].imshow(dA_s, aspect="auto", origin="lower", extent=extent,
                   cmap="terrain", vmin=0, vmax=vmax)
    axes[0].set_title(f"A: scan_{scan_a_num:03d} (reference)")
    axes[0].set_xlabel("phi (rad)")
    axes[0].set_ylabel("eV")

    axes[1].imshow(dB_s, aspect="auto", origin="lower", extent=extent,
                   cmap="terrain", vmin=0, vmax=vmax)
    axes[1].set_title(f"B: scan_{scan_b_num:03d} (pumped)")
    axes[1].set_xlabel("phi (rad)")

    im = axes[2].imshow(diff, aspect="auto", origin="lower", extent=extent,
                        cmap="RdBu_r", vmin=-dscale, vmax=dscale)
    axes[2].set_title("B − A  (differential)")
    axes[2].set_xlabel("phi (rad)")
    plt.colorbar(im, ax=axes[2], label="ΔCounts")

    if show_edc:
        edc_A, phi_idx = compute_edc(dA_s, phi, edc_phi)
        edc_B, _ = compute_edc(dB_s, phi, edc_phi)
        axes[3].plot(eV, edc_A, "b-", lw=1.5, label=f"A (scan_{scan_a_num:03d})")
        axes[3].plot(eV, edc_B, "r-", lw=1.5, label=f"B (scan_{scan_b_num:03d})")
        axes[3].set_xlabel("eV")
        axes[3].set_ylabel("Counts")
        axes[3].set_title(f"EDC at phi = {phi[phi_idx]:.3f} rad")
        axes[3].legend(fontsize=8)
        axes[3].grid(True, alpha=0.3)
        for ax in axes[:3]:
            ax.axvline(phi[phi_idx], color="white", lw=0.8, ls="--", alpha=0.7)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()
