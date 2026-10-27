from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

import core


def _reference_apply_lut(image: np.ndarray, lut: core.CubeLUT) -> np.ndarray:
    """Small-image reference retaining the pre-tile full-frame arithmetic."""
    if image.ndim != 3 or image.shape[-1] != 3:
        raise ValueError("image must have shape (height, width, 3)")
    if not np.issubdtype(image.dtype, np.number) or not np.all(np.isfinite(image)):
        raise ValueError("image must contain finite numeric RGB values")

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
    return np.clip(c0 + fb * (c1 - c0), 0.0, 1.0).astype(np.float32)


def _random_lut(size: int = 9) -> core.CubeLUT:
    rng = np.random.default_rng(7421)
    return core.CubeLUT(
        size=size,
        domain_min=np.array([0.1, -0.1, 0.05], dtype=np.float32),
        domain_max=np.array([0.9, 1.1, 0.95], dtype=np.float32),
        table=rng.random((size, size, size, 3), dtype=np.float32),
    )


@pytest.mark.parametrize("tile_size", [1, 7, 32, 512])
def test_tiled_apply_is_bit_identical_to_legacy_arithmetic(tile_size):
    rng = np.random.default_rng(20261027)
    image = rng.random((37, 53, 3), dtype=np.float32)
    image[0, 0] = (-0.3, 0.5, 1.2)  # exercise clipping at the LUT domain edges
    lut = _random_lut()

    expected = _reference_apply_lut(image, lut)
    actual = core.apply_lut(image, lut, tile_size=tile_size)
    np.testing.assert_array_equal(actual, expected)


def test_apply_lut_rejects_nonfinite_values_even_in_later_tiles():
    image = np.zeros((5, 5, 3), dtype=np.float32)
    image[-1, -1, 0] = np.nan
    with pytest.raises(ValueError, match="finite numeric"):
        core.apply_lut(image, _random_lut(), tile_size=2)


def test_apply_lut_rejects_invalid_tile_size():
    image = np.zeros((2, 2, 3), dtype=np.float32)
    with pytest.raises(ValueError, match="positive integer"):
        core.apply_lut(image, _random_lut(), tile_size=0)


@pytest.mark.skipif(sys.platform != "linux", reason="RSS regression test uses Linux ru_maxrss units")
def test_large_image_peak_rss_is_bounded_by_tiled_processing():
    # Measure the entire peak in a fresh process. ru_maxrss is a process high-water
    # mark, so subtracting two readings from the same process is not reliable.
    script = r'''
import resource
import numpy as np
import core

size = 17
axis = np.linspace(0.0, 1.0, size, dtype=np.float32)
blue, green, red = np.meshgrid(axis, axis, axis, indexing="ij")
table = np.stack((red, green, blue), axis=-1)
lut = core.CubeLUT(
    size=size,
    domain_min=np.zeros(3, dtype=np.float32),
    domain_max=np.ones(3, dtype=np.float32),
    table=table,
)
image = np.random.default_rng(55).random((2400, 3200, 3), dtype=np.float32)
result = core.apply_lut(image, lut, tile_size=256)
assert result.shape == image.shape and result.dtype == np.float32
print(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=True,
    )
    peak_kib = int(completed.stdout.strip().splitlines()[-1])
    peak_bytes = peak_kib * 1024
    image_bytes = 2400 * 3200 * 3 * np.dtype(np.float32).itemsize
    assert peak_bytes < image_bytes * 6, (
        f"peak RSS was {peak_bytes / (1024 ** 2):.0f} MiB for an "
        f"{image_bytes / (1024 ** 2):.0f} MiB image; expected under 6x image bytes"
    )
