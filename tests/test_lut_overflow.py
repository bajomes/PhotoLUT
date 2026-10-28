"""Regression tests for float32 overflow in LUT corner arithmetic.

A .cube table may hold any finite float32 values. When RED-adjacent corners
carry opposite-sign magnitudes near FLT_MAX, the pure-float32 corner
difference (c001 - c000) overflows to -inf; downstream stages (which run in
float64 because frac = norm - idx0 promotes) propagate NaN, np.clip passes
NaN through unchanged, and before the guard apply_lut returned an all-NaN
image. _quantize_rows then cast NaN to 0, producing silently black
TIFF/JPEG exports with a DONE job status.

Blue-axis sign flips do NOT overflow: (c1 - c0) is evaluated in float64.
That behavior is pinned here so future dtype changes are caught.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import core

BIG = "3.000000e+38"  # finite float32 (< 3.4028235e38 = float32 max)


def _write_corner_cube(path: Path, value_for) -> Path:
    rows = []
    for b in (0, 1):
        for g in (0, 1):
            for r in (0, 1):
                v = value_for(b, g, r)
                rows.append(f"{v} {v} {v}")
    path.write_text(
        'TITLE "overflow regression"\nLUT_3D_SIZE 2\n' + "\n".join(rows) + "\n",
        encoding="utf-8",
    )
    return path


def _red_axis_overflow_cube(tmp_path: Path) -> Path:
    return _write_corner_cube(
        tmp_path / "red_overflow.cube",
        lambda b, g, r: BIG if r == 0 else "-" + BIG,
    )


def _blue_axis_extreme_cube(tmp_path: Path) -> Path:
    return _write_corner_cube(
        tmp_path / "blue_extreme.cube",
        lambda b, g, r: BIG if b == 0 else "-" + BIG,
    )


def test_parse_cube_accepts_extreme_finite_values(tmp_path):
    """No arbitrary magnitude cap: any finite float32 table stays parseable."""
    lut = core.parse_cube(_red_axis_overflow_cube(tmp_path))
    assert np.all(np.isfinite(lut.table))
    assert float(np.abs(lut.table).max()) > 1e38


def test_red_axis_overflow_raises_value_error(tmp_path):
    """Repro: before the guard this silently returned an all-NaN image."""
    lut = core.parse_cube(_red_axis_overflow_cube(tmp_path))
    image = np.full((64, 64, 3), 0.5, dtype=np.float32)
    with pytest.raises(ValueError, match="non-finite"):
        core.apply_lut(image, lut)


def test_red_axis_overflow_raises_even_at_corner_pixels(tmp_path):
    """frac == 0 gives 0 * inf -> NaN in the very first stage; must still raise."""
    lut = core.parse_cube(_red_axis_overflow_cube(tmp_path))
    image = np.zeros((8, 8, 3), dtype=np.float32)
    with pytest.raises(ValueError, match="non-finite"):
        core.apply_lut(image, lut)


def test_blue_axis_extreme_values_stay_finite(tmp_path):
    """Blue-direction differences run in float64; must NOT raise."""
    lut = core.parse_cube(_blue_axis_extreme_cube(tmp_path))
    for value in (0.0, 0.25, 0.5, 0.75, 1.0):
        image = np.full((16, 16, 3), value, dtype=np.float32)
        out = core.apply_lut(image, lut)
        assert np.all(np.isfinite(out)), f"non-finite output at input {value}"
        assert 0.0 <= float(out.min()) and float(out.max()) <= 1.0


def test_guard_keeps_normal_lut_output_bit_identical():
    rng = np.random.default_rng(20261027)
    image = rng.random((300, 500, 3), dtype=np.float32)

    size = 17
    xs = np.linspace(0.0, 1.0, size, dtype=np.float32)
    b_i, g_i, r_i = np.meshgrid(
        np.arange(size), np.arange(size), np.arange(size), indexing="ij"
    )
    table = np.stack([
        np.clip(0.9 * xs[r_i] + 0.05, 0.0, 1.0),
        np.clip(xs[g_i], 0.0, 1.0),
        np.clip(0.8 * xs[b_i], 0.0, 1.0),
    ], axis=-1).astype(np.float32)
    lut = core.CubeLUT(
        size=size,
        domain_min=np.array([0.0, 0.0, 0.0], dtype=np.float32),
        domain_max=np.array([1.0, 1.0, 1.0], dtype=np.float32),
        table=table,
    )

    img = np.clip(image, lut.domain_min, lut.domain_max)
    norm = (img - lut.domain_min) / (lut.domain_max - lut.domain_min) * (lut.size - 1)
    idx0 = np.floor(norm).astype(np.int32)
    idx1 = np.minimum(idx0 + 1, lut.size - 1)
    frac = norm - idx0
    r0, g0, b0 = idx0[..., 0], idx0[..., 1], idx0[..., 2]
    r1, g1, b1 = idx1[..., 0], idx1[..., 1], idx1[..., 2]
    fr, fg, fb = frac[..., 0:1], frac[..., 1:2], frac[..., 2:3]
    t = lut.table
    c000 = t[b0, g0, r0]; c001 = t[b0, g0, r1]
    c010 = t[b0, g1, r0]; c011 = t[b0, g1, r1]
    c100 = t[b1, g0, r0]; c101 = t[b1, g0, r1]
    c110 = t[b1, g1, r0]; c111 = t[b1, g1, r1]
    c00 = c000 + fr * (c001 - c000)
    c01 = c010 + fr * (c011 - c010)
    c10 = c100 + fr * (c101 - c100)
    c11 = c110 + fr * (c111 - c110)
    c0 = c00 + fg * (c01 - c00)
    c1 = c10 + fg * (c11 - c10)
    expected = np.clip(c0 + fb * (c1 - c0), 0.0, 1.0).astype(np.float32)

    np.testing.assert_array_equal(core.apply_lut(image, lut), expected)
    np.testing.assert_array_equal(core.apply_lut(image, lut, tile_size=64), expected)
