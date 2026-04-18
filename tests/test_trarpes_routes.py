"""
FastAPI route tests for /trarpes/* endpoints.

These use starlette's TestClient and patch `analysis.trarpes.load_scan`
so that the route code is exercised without requiring real .pxt files.
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest
import xarray as xr

from fastapi.testclient import TestClient


def _synthetic_ds(n_e=20, n_phi=15, *, seed=0):
    rng = np.random.default_rng(seed)
    eV = np.linspace(-1.0, 0.2, n_e)
    phi = np.linspace(-0.1, 0.1, n_phi)
    EV, PHI = np.meshgrid(eV, phi, indexing="ij")
    data = np.exp(-((EV + 0.3) ** 2) / 0.05 - (PHI ** 2) / 0.002)
    data = data + 0.01 * rng.standard_normal(data.shape)
    da = xr.DataArray(data, dims=("eV", "phi"), coords={"eV": eV, "phi": phi})
    return xr.Dataset({"spectrum": da})


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A TestClient with TRARPES_DATA_DIR pointed at a temp dir."""
    monkeypatch.setenv("TRARPES_DATA_DIR", str(tmp_path))

    # Reload the config + route modules so they pick up the env var.
    import importlib

    import app.config as config_mod

    importlib.reload(config_mod)
    import app.routes.trarpes as trarpes_route_mod

    importlib.reload(trarpes_route_mod)

    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(trarpes_route_mod.router)
    return TestClient(app), tmp_path


# ─── GET /trarpes/scans ────────────────────────────────────────────────────────


def test_list_scans_empty(client):
    c, tmp = client
    r = c.get("/trarpes/scans")
    assert r.status_code == 200
    j = r.json()
    assert j["scans"] == []
    assert j["data_dir"] == str(tmp)


def test_list_scans_with_files(client):
    c, tmp = client
    (tmp / "scan_030.pxt").write_bytes(b"stub")
    (tmp / "scan_031.pxt").write_bytes(b"stub")
    (tmp / "scan_030.txt").write_text("Region Name=cut1\n")
    r = c.get("/trarpes/scans")
    assert r.status_code == 200
    scans = r.json()["scans"]
    assert len(scans) == 2
    nums = [s["num"] for s in scans]
    assert nums == [30, 31]
    info = {s["num"]: s["info"] for s in scans}
    assert info[30] == "cut1"
    assert info[31] == ""


# ─── POST /trarpes/upload ──────────────────────────────────────────────────────


def test_upload_accepts_valid_pxt(client):
    c, tmp = client
    files = {"pxt": ("scan_042.pxt", b"fake igor bytes", "application/octet-stream")}
    r = c.post("/trarpes/upload", files=files)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ok"] is True
    assert j["scan_num"] == 42
    assert (tmp / "scan_042.pxt").exists()


def test_upload_with_sidecar_txt(client):
    c, tmp = client
    files = {
        "pxt": ("scan_042.pxt", b"fake", "application/octet-stream"),
        "txt": ("scan_042.txt", b"Region Name=cut42\n", "text/plain"),
    }
    r = c.post("/trarpes/upload", files=files)
    assert r.status_code == 200, r.text
    assert (tmp / "scan_042.pxt").exists()
    assert (tmp / "scan_042.txt").exists()
    assert (tmp / "scan_042.txt").read_text() == "Region Name=cut42\n"


def test_upload_rejects_non_pxt(client):
    c, _ = client
    files = {"pxt": ("something.csv", b"a,b\n1,2\n", "text/csv")}
    r = c.post("/trarpes/upload", files=files)
    assert r.status_code == 400
    assert ".pxt" in r.json()["detail"]


def test_upload_rejects_bad_filename(client):
    c, _ = client
    files = {"pxt": ("weirdname.pxt", b"fake", "application/octet-stream")}
    r = c.post("/trarpes/upload", files=files)
    assert r.status_code == 400
    assert "scan_NNN" in r.json()["detail"]


def test_two_uploads_both_appear_in_scans(client):
    """TR-ARPES comparison needs two files; the frontend uploads sequentially.

    Verifies that after two separate uploads (the pattern the widget uses
    when the user drops two .pxt files at once), both scans are visible
    via /trarpes/scans and are ready to compare.
    """
    c, tmp = client
    r1 = c.post(
        "/trarpes/upload",
        files={"pxt": ("scan_030.pxt", b"ref", "application/octet-stream")},
    )
    r2 = c.post(
        "/trarpes/upload",
        files={"pxt": ("scan_031.pxt", b"pumped", "application/octet-stream")},
    )
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["scan_num"] == 30
    assert r2.json()["scan_num"] == 31

    listing = c.get("/trarpes/scans").json()["scans"]
    assert [s["num"] for s in listing] == [30, 31]


def test_upload_rejects_sidecar_non_txt(client):
    c, _ = client
    files = {
        "pxt": ("scan_042.pxt", b"fake", "application/octet-stream"),
        "txt": ("scan_042.md", b"some markdown", "text/plain"),
    }
    r = c.post("/trarpes/upload", files=files)
    assert r.status_code == 400


# ─── POST /trarpes/compute ─────────────────────────────────────────────────────


def test_compute_returns_panels(client):
    c, tmp = client
    # Touch fake .pxt files so the route won't 404 at pre-checks.
    (tmp / "scan_030.pxt").write_bytes(b"stub")
    (tmp / "scan_031.pxt").write_bytes(b"stub")

    ds_a = _synthetic_ds(seed=1)
    ds_b = _synthetic_ds(seed=2)

    import app.routes.trarpes as routes

    with patch.object(routes, "load_scan", side_effect=[ds_a, ds_b]):
        r = c.post(
            "/trarpes/compute",
            json={"scan_a": 30, "scan_b": 31, "smoothing": 0.5},
        )
    assert r.status_code == 200, r.text
    j = r.json()
    for key in ("eV", "phi", "specA", "specB", "diff", "vmax", "abs_diff_sorted"):
        assert key in j
    assert j["scan_a"] == 30
    assert j["scan_b"] == 31
    assert len(j["specA"]) == len(j["eV"])
    assert len(j["specA"][0]) == len(j["phi"])


def test_compute_surfaces_loader_error(client):
    c, _ = client

    import app.routes.trarpes as routes

    def boom(num, data_dir):
        raise FileNotFoundError(f"no scan_{num:03d}.pxt in {data_dir}")

    with patch.object(routes, "load_scan", side_effect=boom):
        r = c.post(
            "/trarpes/compute",
            json={"scan_a": 99, "scan_b": 100, "smoothing": 0.0},
        )
    assert r.status_code == 404


def test_compute_surfaces_compute_error(client):
    c, _ = client

    import app.routes.trarpes as routes

    ds = _synthetic_ds()
    with patch.object(routes, "load_scan", return_value=ds), \
         patch.object(routes, "compute_panels", side_effect=RuntimeError("bad shape")):
        r = c.post(
            "/trarpes/compute",
            json={"scan_a": 30, "scan_b": 31, "smoothing": 0.0},
        )
    assert r.status_code == 500
    assert "bad shape" in r.json()["detail"]


# ─── POST /trarpes/export ──────────────────────────────────────────────────────


def test_export_returns_png(client):
    c, tmp = client

    ds_a = _synthetic_ds(seed=3)
    ds_b = _synthetic_ds(seed=4)

    import app.routes.trarpes as routes

    with patch.object(routes, "load_scan", side_effect=[ds_a, ds_b]):
        r = c.post(
            "/trarpes/export",
            json={
                "scan_a": 30,
                "scan_b": 31,
                "smoothing": 0.0,
                "diff_scale_pct": 95.0,
                "show_edc": False,
                "edc_phi": 0.0,
            },
        )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "image/png"
    assert "attachment" in r.headers["content-disposition"]
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
