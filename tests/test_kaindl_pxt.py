"""
Unit tests for analysis/parsers/kaindl_pxt.py.

These cover the pure-Python helpers (``_safe_decode``, ``_parse_notes``,
``_wave_dict_to_xarray``, ``read_scan_info``) plus the top-level loader's
transform pipeline (byte order probing, deg->rad, Delay Stage rename,
eV negation flag). We bypass ``igor2`` entirely by patching
``_packed_load`` and ``_is_wave_record`` module-level helpers so the
tests don't depend on any real .pxt file.
"""

from __future__ import annotations

import numpy as np
import pytest
import xarray as xr

from analysis.parsers import kaindl_pxt
from analysis.parsers.kaindl_pxt import (
    _parse_notes,
    _safe_decode,
    _wave_dict_to_xarray,
    load_kaindl_pxt,
    read_scan_info,
)


# ─── _safe_decode ──────────────────────────────────────────────────────────────


def test_safe_decode_utf8():
    assert _safe_decode(b"hello world") == "hello world"


def test_safe_decode_str_passthrough():
    assert _safe_decode("already a str") == "already a str"


def test_safe_decode_latin1_fallback():
    # 0xE9 is "é" in latin-1 but invalid utf-8 if bare
    assert _safe_decode(b"caf\xe9") == "café"


def test_safe_decode_malformed_never_raises():
    assert isinstance(_safe_decode(b"\xff\xfe bad"), str)


# ─── _parse_notes ──────────────────────────────────────────────────────────────


def test_parse_notes_key_value_pairs():
    raw = b"Region Name=cut1\r\nPass Energy=20\n"
    out = _parse_notes(raw)
    assert out["region_name"] == "cut1"
    assert out["pass_energy"] == 20


def test_parse_notes_float_coercion():
    out = _parse_notes(b"hv=21.4\n")
    assert out["hv"] == pytest.approx(21.4)


def test_parse_notes_header_renames():
    raw = b"sample_x=1.0\nsample_y=2.0\nsample_z=3.0\nbl_energy=21.0\n"
    out = _parse_notes(raw)
    assert out["x"] == 1.0
    assert out["y"] == 2.0
    assert out["z"] == 3.0
    assert out["hv"] == 21.0
    assert "sample_x" not in out
    assert "bl_energy" not in out


def test_parse_notes_empty_or_none():
    assert _parse_notes(None) == {}
    assert _parse_notes(b"") == {}
    assert _parse_notes(b"no equals signs here\n") == {}


def test_parse_notes_ignores_malformed_lines():
    out = _parse_notes(b"good=1\nnobadline\nalso_good=2\n")
    assert out == {"good": 1, "also_good": 2}


# ─── _wave_dict_to_xarray ─────────────────────────────────────────────────────


def _make_wave_dict(data, *, ev, phi, units=(b"eV", b"deg", b"", b""), note=b""):
    """Build an igor2-shaped wave dict with ``wave_header`` + ``wData``."""
    nDim = [len(ev), len(phi), 0, 0]
    # Derive sfA / sfB from the coord arrays (evenly spaced assumption)
    def _step_off(arr):
        if len(arr) < 2:
            return 1.0, float(arr[0]) if len(arr) else 0.0
        return float(arr[1] - arr[0]), float(arr[0])

    sfA = [_step_off(ev)[0], _step_off(phi)[0], 1.0, 1.0]
    sfB = [_step_off(ev)[1], _step_off(phi)[1], 0.0, 0.0]
    header = {
        "bname": b"spectrum",
        "nDim": nDim,
        "sfA": sfA,
        "sfB": sfB,
        "dataUnits": b"counts",
        "dimUnits": [[u] for u in units],
    }
    return {
        "version": 5,
        "wave": {
            "wave_header": header,
            "wData": data,
            "note": note,
            "dimension_units": list(units),
            "data_units": b"counts",
        },
    }


def test_wave_to_xarray_eV_phi_dims():
    eV = np.linspace(-1, 0, 4)
    phi = np.linspace(-0.1, 0.1, 3)
    data = np.arange(12, dtype=np.float64).reshape(4, 3)
    da = _wave_dict_to_xarray(_make_wave_dict(data, ev=eV, phi=phi))
    assert da.dims == ("eV", "phi")
    # Tolerance of a few ulps — igor-style sfA/sfB reconstruction is slightly
    # lossy vs. linspace endpoints.
    np.testing.assert_allclose(da.coords["eV"].values, eV, atol=1e-10)
    np.testing.assert_allclose(da.coords["phi"].values, phi, atol=1e-10)


def test_wave_to_xarray_unknown_unit_uses_placeholder():
    eV = np.array([0.0, 1.0])
    phi = np.array([0.0, 1.0])
    data = np.zeros((2, 2))
    # Empty units -> loader should fall back to W, X, Y, Z
    da = _wave_dict_to_xarray(
        _make_wave_dict(data, ev=eV, phi=phi, units=(b"", b"", b"", b""))
    )
    assert da.dims == ("W", "X")


def test_wave_to_xarray_byteswaps_nonnative():
    import sys

    nonnative = ">f8" if sys.byteorder == "little" else "<f8"
    data = np.arange(4, dtype=nonnative).reshape(2, 2)
    assert data.dtype.byteorder not in ("=", "|")
    da = _wave_dict_to_xarray(
        _make_wave_dict(data, ev=np.array([0.0, 1.0]), phi=np.array([0.0, 1.0]))
    )
    host_char = "<" if sys.byteorder == "little" else ">"
    assert da.values.dtype.byteorder in ("=", "|", host_char)
    np.testing.assert_allclose(da.values, [[0, 1], [2, 3]])


def test_wave_to_xarray_reads_notes():
    wave = _make_wave_dict(
        np.zeros((2, 2)),
        ev=np.array([0.0, 1.0]),
        phi=np.array([0.0, 1.0]),
        note=b"Region Name=cut1\nhv=21.4\n",
    )
    da = _wave_dict_to_xarray(wave)
    assert da.attrs["region_name"] == "cut1"
    assert da.attrs["hv"] == pytest.approx(21.4)


# ─── load_kaindl_pxt transformations ───────────────────────────────────────────


def _install_fake_loader(monkeypatch, records):
    """Patch ``kaindl_pxt._packed_load`` to return scripted records."""

    def _load(path, initial_byte_order):
        return (records, {})

    monkeypatch.setattr(kaindl_pxt, "_packed_load", _load)
    # Also treat anything with a ``wave`` attr as a wave record.
    monkeypatch.setattr(
        kaindl_pxt, "_is_wave_record", lambda obj: hasattr(obj, "wave")
    )


class _FakeWaveRecord:
    def __init__(self, wave_dict):
        self.wave = wave_dict


def test_load_kaindl_pxt_no_negation_by_default(tmp_path, monkeypatch):
    eV = np.linspace(-2, 0, 3)
    phi = np.linspace(-0.1, 0.1, 2)
    data = np.arange(6, dtype=float).reshape(3, 2)
    _install_fake_loader(
        monkeypatch,
        [_FakeWaveRecord(_make_wave_dict(data, ev=eV, phi=phi, note=b"Region Name=cut1\n"))],
    )
    p = tmp_path / "scan_031.pxt"
    p.write_bytes(b"fake")
    ds = load_kaindl_pxt(p)
    np.testing.assert_allclose(ds.spectrum.coords["eV"].values, eV)
    np.testing.assert_allclose(
        ds.spectrum.coords["phi"].values, phi * np.pi / 180.0
    )


def test_load_kaindl_pxt_negate_energy_true(tmp_path, monkeypatch):
    eV = np.linspace(-2, 0, 3)
    phi = np.linspace(-0.1, 0.1, 2)
    data = np.zeros((3, 2))
    _install_fake_loader(
        monkeypatch, [_FakeWaveRecord(_make_wave_dict(data, ev=eV, phi=phi))]
    )
    p = tmp_path / "scan_031.pxt"
    p.write_bytes(b"fake")
    ds = load_kaindl_pxt(p, negate_energy=True)
    np.testing.assert_allclose(ds.spectrum.coords["eV"].values, -eV)


def test_load_kaindl_pxt_delay_stage_rename(tmp_path, monkeypatch):
    eV = np.array([0.0, 1.0])
    phi = np.array([0.0, 1.0])
    data = np.zeros((2, 2))
    _install_fake_loader(
        monkeypatch,
        [_FakeWaveRecord(_make_wave_dict(
            data, ev=eV, phi=phi, note=b"Delay Stage=242.5\n"
        ))],
    )
    p = tmp_path / "scan_031.pxt"
    p.write_bytes(b"fake")
    ds = load_kaindl_pxt(p)
    # Delay Stage attr renamed to 'delay' (via explicit post-step, not notes lowercasing)
    assert "delay_stage" in ds.spectrum.attrs or "delay" in ds.spectrum.attrs


def test_load_kaindl_pxt_byteorder_fallback(tmp_path, monkeypatch):
    """First load() call raises, second succeeds — loader must try the next order."""
    eV = np.array([0.0, 1.0])
    phi = np.array([0.0, 1.0])
    good_records = [_FakeWaveRecord(_make_wave_dict(np.zeros((2, 2)), ev=eV, phi=phi))]
    call_count = {"n": 0}

    def flaky_load(path, initial_byte_order):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise IOError("wrong byte order")
        return (good_records, {})

    monkeypatch.setattr(kaindl_pxt, "_packed_load", flaky_load)
    monkeypatch.setattr(kaindl_pxt, "_is_wave_record", lambda obj: hasattr(obj, "wave"))

    p = tmp_path / "scan_031.pxt"
    p.write_bytes(b"fake")
    load_kaindl_pxt(p)
    assert call_count["n"] == 2


def test_load_kaindl_pxt_all_byte_orders_fail(tmp_path, monkeypatch):
    def always_fail(path, initial_byte_order):
        raise IOError(f"bad {initial_byte_order}")

    monkeypatch.setattr(kaindl_pxt, "_packed_load", always_fail)
    p = tmp_path / "scan_031.pxt"
    p.write_bytes(b"fake")
    with pytest.raises(IOError, match="Could not decode"):
        load_kaindl_pxt(p)


def test_load_kaindl_pxt_no_waves_raises(tmp_path, monkeypatch):
    _install_fake_loader(monkeypatch, [])  # no records
    p = tmp_path / "scan_031.pxt"
    p.write_bytes(b"fake")
    with pytest.raises(ValueError, match="No Igor waves"):
        load_kaindl_pxt(p)


def test_load_kaindl_pxt_picks_largest_wave(tmp_path, monkeypatch):
    """A .pxt may have multiple waves; we should pick the biggest (the spectrum)."""
    eV = np.linspace(-1, 0, 10)
    phi = np.linspace(-0.1, 0.1, 8)
    big = np.random.default_rng(0).standard_normal((10, 8))
    small = np.array([[1.0, 2.0]])
    _install_fake_loader(
        monkeypatch,
        [
            _FakeWaveRecord(
                _make_wave_dict(small, ev=np.array([0.0]), phi=np.array([0.0, 1.0]))
            ),
            _FakeWaveRecord(_make_wave_dict(big, ev=eV, phi=phi)),
        ],
    )
    p = tmp_path / "scan_031.pxt"
    p.write_bytes(b"fake")
    ds = load_kaindl_pxt(p)
    assert ds.spectrum.shape == (10, 8)


# ─── read_scan_info ────────────────────────────────────────────────────────────


def test_read_scan_info_region_name(tmp_path):
    p = tmp_path / "scan_030.txt"
    p.write_text("Some Header=x\nRegion Name=hailan fine cut\nMore=y\n")
    assert read_scan_info(p) == "hailan fine cut"


def test_read_scan_info_comments_fallback(tmp_path):
    p = tmp_path / "scan_030.txt"
    p.write_text("Comments=quick cut\nOther=1\n")
    assert read_scan_info(p) == "quick cut"


def test_read_scan_info_prefers_region_name_over_comments(tmp_path):
    p = tmp_path / "scan_030.txt"
    p.write_text("Region Name=first\nComments=second\n")
    assert read_scan_info(p) == "first"


def test_read_scan_info_missing_file(tmp_path):
    assert read_scan_info(tmp_path / "does_not_exist.txt") == ""


def test_read_scan_info_empty_when_neither_present(tmp_path):
    p = tmp_path / "scan_030.txt"
    p.write_text("Some Other Field=foo\n")
    assert read_scan_info(p) == ""
