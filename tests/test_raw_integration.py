from __future__ import annotations

import os
import shutil
from pathlib import Path

import numpy as np
import pytest
import tifffile
from PIL import Image

import app
import core


RAW_FIXTURE_DIR = Path(os.environ.get("PHOTOLUT_TEST_RAW_DIR", "test-data"))
RAW_FIXTURES = ("iss030e122639.NEF", "iss042e297200.NEF")


def write_cube(path: Path, transform) -> Path:
    """Write a 2x2x2 .cube; entries are ordered with red varying fastest."""
    rows = []
    for blue in (0.0, 1.0):
        for green in (0.0, 1.0):
            for red in (0.0, 1.0):
                rows.append(" ".join(f"{channel:.8f}" for channel in transform(red, green, blue)))
    path.write_text(
        "TITLE \"PhotoLUT integration test\"\n"
        "LUT_3D_SIZE 2\n"
        + "\n".join(rows)
        + "\n",
        encoding="utf-8",
    )
    return path


def creative_transform(red: np.ndarray, green: np.ndarray, blue: np.ndarray):
    # Mild warm look: gently lift red, slightly compress green, reduce blue.
    return (
        0.97 * red + 0.03,
        0.98 * green,
        0.88 * blue,
    )


@pytest.mark.parametrize("filename", RAW_FIXTURES)
def test_real_raw_identity_and_creative_luts_export_correctly(tmp_path, filename):
    raw_path = RAW_FIXTURE_DIR / filename
    if not raw_path.is_file():
        pytest.skip(f"RAW integration fixture is not present: {raw_path}")
    if shutil.which("exiftool") is None:
        pytest.skip("ExifTool is required for the metadata integration check")

    image = core.decode_raw(raw_path)
    assert image.ndim == 3 and image.shape[-1] == 3
    assert image.dtype == np.float32
    assert np.all(np.isfinite(image))
    assert float(image.min()) >= 0.0
    assert float(image.max()) <= 1.0

    identity_path = write_cube(tmp_path / "identity.cube", lambda r, g, b: (r, g, b))
    creative_path = write_cube(tmp_path / "warm-creative.cube", creative_transform)

    for label, cube_path in (("identity", identity_path), ("creative", creative_path)):
        lut = core.parse_cube(cube_path)
        graded = core.apply_lut(image, lut)

        if label == "identity":
            np.testing.assert_allclose(graded, image, rtol=0.0, atol=1e-6)
        else:
            expected = np.stack(creative_transform(image[..., 0], image[..., 1], image[..., 2]), axis=-1)
            np.testing.assert_allclose(graded, expected, rtol=0.0, atol=2e-6)
            assert float(graded[..., 2].mean()) < float(image[..., 2].mean())

        out_dir = tmp_path / label
        out_dir.mkdir()
        paths, metadata_ok = app._save_outputs(
            graded, image, out_dir, Path(filename).stem, 0, raw_path
        )
        assert metadata_ok, f"ExifTool failed to copy metadata for {filename} ({label})"

        # TIFF should preserve all 16 bits per channel and the exact quantized pixels.
        tiff = tifffile.imread(paths["tiff"])
        expected_tiff = np.rint(graded * 65535.0).astype(np.uint16)
        assert tiff.dtype == np.uint16
        assert tiff.shape == graded.shape
        np.testing.assert_array_equal(tiff, expected_tiff)
        with tifffile.TiffFile(paths["tiff"]) as tif:
            assert 34675 in tif.pages[0].tags, "TIFF lost its embedded sRGB ICC profile"
            orientation_tag = tif.pages[0].tags.get(274)
            assert orientation_tag is None or int(orientation_tag.value) == 1

        # JPEG should remain RGB, retain an ICC profile, and declare normal orientation.
        with Image.open(paths["jpeg"]) as jpeg:
            assert jpeg.mode == "RGB"
            assert jpeg.size == (graded.shape[1], graded.shape[0])
            assert jpeg.info.get("icc_profile"), "JPEG lost its embedded sRGB ICC profile"
            exif = jpeg.getexif()
            assert exif.get(274, 1) == 1, "JPEG orientation must be normalized to 1"
            assert exif.get(271) or exif.get(272), "Camera make/model metadata was not copied"

        # The comparison previews should also advertise the display RGB profile.
        with Image.open(paths["preview_after"]) as preview:
            assert preview.info.get("icc_profile")

        del expected_tiff, tiff, graded
