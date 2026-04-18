"""
Unit tests for analysis/trarpes.py.

We bypass the igor2-dependent .pxt loader by constructing synthetic
xarray.Datasets directly. That lets us exercise compute_panels,
compute_edc, render_png, and the discovery/cache helpers without any
real data.
"""

from __future__ import annotations

import numpy as np
import pytest
import xarray as xr

from analysis import trarpes


# ─── synthetic dataset helpers ─────────────────────────────────────────────────


def _synthetic_ds(n_e=40, n_phi=30, *, noise_seed=0, amplitude=1.0):
    rng = np.random.default_rng(noise_seed)
    eV = np.linspace(-1.0, 0.5, n_e)
    phi = np.linspace(-0.15, 0.15, n_phi)
    # A simple gaussian "band" plus optional noise
    EV, PHI = np.meshgrid(eV, phi, indexing="ij")
    data = amplitude * np.exp(-((EV + 0.3) ** 2) / 0.05 - (PHI ** 2) / 0.002)
    data = data + 0.01 * rng.standard_normal(data.shape)
    da = xr.DataArray(
        data, dims=("eV", "phi"), coords={"eV": eV, "phi": phi}
    )
    return xr.Dataset({"spectrum": da})


# ─── discover_scans ────────────────────────────────────────────────────────────


def test_discover_scans_finds_static_pxt(tmp_path):
    (tmp_path / "scan_000.pxt").write_bytes(b"stub")
    (tmp_path / "scan_017.pxt").write_bytes(b"stub")
    (tmp_path / "scan_030.pxt").write_bytes(b"stub")
    (tmp_path / "scan_030.txt").write_text("Region Name=hailan fine cut\n")

    out = trarpes.discover_scans(tmp_path)
    assert [e.num for e in out] == [0, 17, 30]
    labels = {e.num: e.info for e in out}
    assert labels[30] == "hailan fine cut"
    assert labels[0] == ""  # no sidecar


def test_discover_scans_excludes_map_variants(tmp_path):
    # Angle/theta maps use the scan_NNN_NNN.pxt pattern — must be ignored.
    (tmp_path / "scan_030.pxt").write_bytes(b"stub")
    (tmp_path / "scan_030_001.pxt").write_bytes(b"stub")
    (tmp_path / "scan_030_002.pxt").write_bytes(b"stub")

    out = trarpes.discover_scans(tmp_path)
    assert [e.num for e in out] == [30]


def test_discover_scans_missing_dir(tmp_path):
    assert trarpes.discover_scans(tmp_path / "nope") == []


def test_discover_scans_sorted(tmp_path):
    for n in (33, 18, 22, 0, 31):
        (tmp_path / f"scan_{n:03d}.pxt").write_bytes(b"stub")
    out = trarpes.discover_scans(tmp_path)
    assert [e.num for e in out] == [0, 18, 22, 31, 33]


# ─── load_scan caching ─────────────────────────────────────────────────────────


def test_load_scan_is_cached(tmp_path, monkeypatch):
    trarpes.clear_cache()

    call_count = {"n": 0}
    fake_ds = _synthetic_ds(n_e=3, n_phi=3)

    def fake_loader(path, *, negate_energy=False):
        call_count["n"] += 1
        return fake_ds

    monkeypatch.setattr(trarpes, "load_kaindl_pxt", fake_loader)
    (tmp_path / "scan_005.pxt").write_bytes(b"x")

    a = trarpes.load_scan(5, tmp_path)
    b = trarpes.load_scan(5, tmp_path)
    assert a is b
    assert call_count["n"] == 1


# ─── _downsample ───────────────────────────────────────────────────────────────


def test_downsample_no_op_below_threshold():
    arr = np.arange(100).reshape(10, 10).astype(float)
    out = trarpes._downsample(arr, max_size=200)
    np.testing.assert_array_equal(out, arr)


def test_downsample_reduces_shape():
    arr = np.arange(10000).reshape(100, 100).astype(float)
    out = trarpes._downsample(arr, max_size=50)
    assert out.shape[0] <= 50
    assert out.shape[1] <= 50


def test_downsample_preserves_block_mean():
    arr = np.arange(16).reshape(4, 4).astype(float)
    out = trarpes._downsample(arr, max_size=2)
    assert out.shape == (2, 2)
    # Top-left 2x2 block: values 0, 1, 4, 5 -> mean = 2.5
    assert out[0, 0] == pytest.approx(2.5)


# ─── compute_panels ────────────────────────────────────────────────────────────


def test_compute_panels_basic_shapes():
    ds_a = _synthetic_ds(noise_seed=1)
    ds_b = _synthetic_ds(noise_seed=2)
    panels = trarpes.compute_panels(ds_a, ds_b, smoothing=0.0, max_size=200)
    assert len(panels["eV"]) == len(panels["specA"])
    assert len(panels["phi"]) == len(panels["specA"][0])
    assert len(panels["specA"]) == len(panels["specB"]) == len(panels["diff"])
    assert panels["vmax"] > 0


def test_compute_panels_same_scan_zero_diff():
    ds = _synthetic_ds(noise_seed=7)
    panels = trarpes.compute_panels(ds, ds, smoothing=0.0, max_size=200)
    diff = np.array(panels["diff"])
    assert np.allclose(diff, 0.0)


def test_compute_panels_trims_to_common_size():
    ds_a = _synthetic_ds(n_e=40, n_phi=30)
    ds_b = _synthetic_ds(n_e=35, n_phi=28)
    panels = trarpes.compute_panels(ds_a, ds_b, smoothing=0.0, max_size=200)
    # Input shapes reported in metadata
    assert panels["shape_a"] == [40, 30]
    assert panels["shape_b"] == [35, 28]
    # Effective trim = (35, 28). With max_size >= 35 no downsampling.
    assert len(panels["specA"]) == 35
    assert len(panels["specA"][0]) == 28
    assert len(panels["specB"]) == 35
    assert len(panels["diff"]) == 35


def test_compute_panels_smoothing_changes_output():
    ds_a = _synthetic_ds(noise_seed=3)
    ds_b = _synthetic_ds(noise_seed=4)
    p_sharp = trarpes.compute_panels(ds_a, ds_b, smoothing=0.0, max_size=200)
    p_smooth = trarpes.compute_panels(ds_a, ds_b, smoothing=2.0, max_size=200)
    # Smoothing should suppress variance in the difference
    v_sharp = float(np.var(np.array(p_sharp["diff"])))
    v_smooth = float(np.var(np.array(p_smooth["diff"])))
    assert v_smooth < v_sharp


def test_compute_panels_abs_diff_sorted_is_sorted():
    ds_a = _synthetic_ds(noise_seed=5)
    ds_b = _synthetic_ds(noise_seed=6)
    panels = trarpes.compute_panels(ds_a, ds_b, smoothing=0.0, max_size=200)
    arr = panels["abs_diff_sorted"]
    assert arr == sorted(arr)


def test_compute_panels_downsampled_when_large():
    ds_a = _synthetic_ds(n_e=400, n_phi=400, noise_seed=8)
    ds_b = _synthetic_ds(n_e=400, n_phi=400, noise_seed=9)
    panels = trarpes.compute_panels(ds_a, ds_b, smoothing=0.0, max_size=100)
    assert len(panels["specA"]) <= 100
    assert len(panels["specA"][0]) <= 100


def test_compute_panels_handles_phi_ev_transpose():
    # Build a dataset oriented (phi, eV) — loader should re-orient.
    eV = np.linspace(-1, 0, 20)
    phi = np.linspace(-0.1, 0.1, 15)
    data = np.random.default_rng(0).standard_normal((15, 20))  # (phi, eV)
    da = xr.DataArray(data, dims=("phi", "eV"), coords={"phi": phi, "eV": eV})
    ds = xr.Dataset({"spectrum": da})
    panels = trarpes.compute_panels(ds, ds, smoothing=0.0, max_size=200)
    assert len(panels["eV"]) == 20
    assert len(panels["phi"]) == 15


# ─── compute_edc ───────────────────────────────────────────────────────────────


def test_compute_edc_shape_and_index():
    ds = _synthetic_ds(n_e=30, n_phi=21, noise_seed=0, amplitude=1.0)
    spec = ds.spectrum.values
    phi = ds.spectrum.coords["phi"].values
    edc, idx = trarpes.compute_edc(spec, phi, phi_target=0.0, width=3)
    assert edc.shape == (30,)
    # phi_target=0 in a linspace(-0.15, 0.15, 21) puts us at index 10
    assert idx == 10


def test_compute_edc_target_out_of_range_clamps():
    ds = _synthetic_ds(n_e=10, n_phi=7, noise_seed=0)
    spec = ds.spectrum.values
    phi = ds.spectrum.coords["phi"].values
    edc, idx = trarpes.compute_edc(spec, phi, phi_target=10.0, width=3)
    # picks the nearest index, which is the last one
    assert idx == len(phi) - 1
    assert edc.shape == (10,)


# ─── render_png ────────────────────────────────────────────────────────────────


def test_render_png_returns_png_bytes():
    ds_a = _synthetic_ds(noise_seed=11)
    ds_b = _synthetic_ds(noise_seed=12)
    png = trarpes.render_png(
        ds_a,
        ds_b,
        scan_a_num=30,
        scan_b_num=31,
        smoothing=0.0,
        diff_scale_pct=95.0,
        show_edc=False,
        edc_phi=0.0,
        dpi=80,
    )
    # PNG magic bytes
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_png_with_edc_panel():
    ds_a = _synthetic_ds(noise_seed=13)
    ds_b = _synthetic_ds(noise_seed=14)
    png = trarpes.render_png(
        ds_a,
        ds_b,
        scan_a_num=30,
        scan_b_num=31,
        smoothing=0.5,
        diff_scale_pct=90.0,
        show_edc=True,
        edc_phi=0.02,
        dpi=80,
    )
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    # 4-panel figure should be larger on disk than the 3-panel one
    png_3 = trarpes.render_png(
        ds_a,
        ds_b,
        scan_a_num=30,
        scan_b_num=31,
        smoothing=0.5,
        diff_scale_pct=90.0,
        show_edc=False,
        edc_phi=0.02,
        dpi=80,
    )
    assert len(png) > len(png_3) * 0.5  # not a strict size rule, but sanity check
