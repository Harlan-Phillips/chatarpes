"""
Tests for the TR-ARPES compatibility check.

The check must accept 2D (eV, phi) spectra and reject 1D/3D data, wrong
axes, missing files, and loader failures. We patch load_kaindl_pxt with
synthetic xarray.Datasets so we don't need real .pxt files.
"""

from __future__ import annotations

import os

import numpy as np
import xarray as xr

from analysis import trarpes


def _pxt(tmp_path, name, data=b"stub"):
    p = tmp_path / name
    p.write_bytes(data)
    return p


def _good_ds():
    eV = np.linspace(-1, 0, 5)
    phi = np.linspace(-0.1, 0.1, 4)
    da = xr.DataArray(
        np.zeros((5, 4)), dims=("eV", "phi"), coords={"eV": eV, "phi": phi}
    )
    return xr.Dataset({"spectrum": da})


def _1d_ds():
    eV = np.linspace(-1, 0, 5)
    da = xr.DataArray(np.zeros(5), dims=("eV",), coords={"eV": eV})
    return xr.Dataset({"spectrum": da})


def _3d_ds():
    da = xr.DataArray(
        np.zeros((3, 4, 5)),
        dims=("eV", "phi", "delay"),
        coords={
            "eV": np.linspace(-1, 0, 3),
            "phi": np.linspace(-0.1, 0.1, 4),
            "delay": np.arange(5, dtype=float),
        },
    )
    return xr.Dataset({"spectrum": da})


def _wrong_axes_ds():
    # 2D but the dims aren't eV/phi
    x = np.arange(5, dtype=float)
    y = np.arange(4, dtype=float)
    da = xr.DataArray(np.zeros((5, 4)), dims=("x", "y"), coords={"x": x, "y": y})
    return xr.Dataset({"spectrum": da})


# ─── check_trarpes_compat ──────────────────────────────────────────────────────


def test_compat_ok_for_2d_ev_phi(tmp_path, monkeypatch):
    p = _pxt(tmp_path, "scan_030.pxt")
    monkeypatch.setattr(trarpes, "load_kaindl_pxt", lambda _p, **_: _good_ds())
    r = trarpes.check_trarpes_compat(p)
    assert r["ok"] is True
    assert r["shape"] == [5, 4]
    assert set(r["dims"]) == {"eV", "phi"}


def test_compat_rejects_1d(tmp_path, monkeypatch):
    p = _pxt(tmp_path, "scan_030.pxt")
    monkeypatch.setattr(trarpes, "load_kaindl_pxt", lambda _p, **_: _1d_ds())
    r = trarpes.check_trarpes_compat(p)
    assert r["ok"] is False
    assert "2D" in r["reason"]


def test_compat_rejects_3d(tmp_path, monkeypatch):
    p = _pxt(tmp_path, "scan_030.pxt")
    monkeypatch.setattr(trarpes, "load_kaindl_pxt", lambda _p, **_: _3d_ds())
    r = trarpes.check_trarpes_compat(p)
    assert r["ok"] is False
    assert "2D" in r["reason"]


def test_compat_rejects_wrong_axes(tmp_path, monkeypatch):
    p = _pxt(tmp_path, "scan_030.pxt")
    monkeypatch.setattr(trarpes, "load_kaindl_pxt", lambda _p, **_: _wrong_axes_ds())
    r = trarpes.check_trarpes_compat(p)
    assert r["ok"] is False
    # eV is listed first in the check, so the message surfaces that axis
    assert "eV" in r["reason"] or "phi" in r["reason"]


def test_compat_surfaces_loader_error(tmp_path, monkeypatch):
    p = _pxt(tmp_path, "scan_030.pxt")

    def boom(_p, **_):
        raise IOError("unreadable igor file")

    monkeypatch.setattr(trarpes, "load_kaindl_pxt", boom)
    r = trarpes.check_trarpes_compat(p)
    assert r["ok"] is False
    assert "Failed to load" in r["reason"]
    assert "unreadable" in r["reason"]


def test_compat_missing_file(tmp_path):
    # Don't create the file
    r = trarpes.check_trarpes_compat(tmp_path / "missing.pxt")
    assert r["ok"] is False
    assert "not exist" in r["reason"].lower() or "not accessible" in r["reason"].lower()


# ─── cached variant ────────────────────────────────────────────────────────────


def test_cached_compat_avoids_redundant_loads(tmp_path, monkeypatch):
    p = _pxt(tmp_path, "scan_030.pxt")
    calls = {"n": 0}

    def counted_load(_p, **_):
        calls["n"] += 1
        return _good_ds()

    monkeypatch.setattr(trarpes, "load_kaindl_pxt", counted_load)
    trarpes.clear_cache()

    r1 = trarpes.check_trarpes_compat_cached(p)
    r2 = trarpes.check_trarpes_compat_cached(p)
    assert r1 == r2
    assert calls["n"] == 1  # second call served from cache


def test_cached_compat_invalidates_on_mtime_change(tmp_path, monkeypatch):
    p = _pxt(tmp_path, "scan_030.pxt")
    calls = {"n": 0}

    def counted_load(_p, **_):
        calls["n"] += 1
        return _good_ds()

    monkeypatch.setattr(trarpes, "load_kaindl_pxt", counted_load)
    trarpes.clear_cache()

    trarpes.check_trarpes_compat_cached(p)
    assert calls["n"] == 1
    # Bump mtime by >1s to avoid fs granularity collisions
    new_mtime = os.path.getmtime(p) + 5
    os.utime(p, (new_mtime, new_mtime))
    trarpes.check_trarpes_compat_cached(p)
    assert calls["n"] == 2


# ─── route wiring ──────────────────────────────────────────────────────────────


def test_scans_endpoint_includes_compat(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setenv("TRARPES_DATA_DIR", str(tmp_path))
    import importlib

    import app.config as cfg
    import app.routes.trarpes as routes

    importlib.reload(cfg)
    importlib.reload(routes)

    (tmp_path / "scan_030.pxt").write_bytes(b"stub")
    (tmp_path / "scan_031.pxt").write_bytes(b"stub")

    call_log = []

    def fake_load(path, **_):
        call_log.append(str(path))
        if "031" in str(path):
            return _1d_ds()  # incompatible
        return _good_ds()

    monkeypatch.setattr(trarpes, "load_kaindl_pxt", fake_load)
    trarpes.clear_cache()

    app = FastAPI()
    app.include_router(routes.router)
    c = TestClient(app)

    # Without the flag, no compat field attached
    r = c.get("/trarpes/scans")
    assert r.status_code == 200
    for s in r.json()["scans"]:
        assert "compat" not in s

    r = c.get("/trarpes/scans?check_compat=true")
    assert r.status_code == 200
    by_num = {s["num"]: s for s in r.json()["scans"]}
    assert by_num[30]["compat"]["ok"] is True
    assert by_num[31]["compat"]["ok"] is False
    assert "2D" in by_num[31]["compat"]["reason"]


def test_upload_response_includes_compat(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setenv("TRARPES_DATA_DIR", str(tmp_path))
    import importlib

    import app.config as cfg
    import app.routes.trarpes as routes

    importlib.reload(cfg)
    importlib.reload(routes)

    monkeypatch.setattr(trarpes, "load_kaindl_pxt", lambda _p, **_: _good_ds())
    trarpes.clear_cache()

    app = FastAPI()
    app.include_router(routes.router)
    c = TestClient(app)

    r = c.post(
        "/trarpes/upload",
        files={"pxt": ("scan_042.pxt", b"stub", "application/octet-stream")},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["compat"]["ok"] is True
    assert set(j["compat"]["dims"]) == {"eV", "phi"}
