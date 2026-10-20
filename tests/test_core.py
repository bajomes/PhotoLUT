from __future__ import annotations

import numpy as np
import pytest

import core


def write_cube(path, transform=lambda r, g, b: (r, g, b), *, domain_header=""):
    rows = []
    for b in (0.0, 1.0):
        for g in (0.0, 1.0):
            for r in (0.0, 1.0):
                out = transform(r, g, b)
                rows.append(" ".join(str(v) for v in out))
    path.write_text(
        f"TITLE \"test\"\nLUT_3D_SIZE 2\n{domain_header}" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )
    return path


def test_identity_lut_preserves_rgb_values(tmp_path):
    path = write_cube(tmp_path / "identity.cube")
    lut = core.parse_cube(path)
    pixels = np.array([[[0, 0, 0], [1, 1, 1], [0.25, 0.5, 0.75]]], dtype=np.float32)

    result = core.apply_lut(pixels, lut)

    np.testing.assert_allclose(result, pixels, atol=1e-6)


def test_cube_channel_order_and_trilinear_interpolation(tmp_path):
    path = write_cube(tmp_path / "swap-red-blue.cube", transform=lambda r, g, b: (b, g, r))
    lut = core.parse_cube(path)
    pixels = np.array([[[0.2, 0.4, 0.8], [0.9, 0.1, 0.3]]], dtype=np.float32)

    result = core.apply_lut(pixels, lut)

    expected = pixels[..., ::-1]
    np.testing.assert_allclose(result, expected, atol=1e-6)


def test_rejects_wrong_number_of_values(tmp_path):
    path = tmp_path / "short.cube"
    path.write_text("LUT_3D_SIZE 2\n0 0 0\n", encoding="utf-8")

    with pytest.raises(ValueError, match="expected exactly"):
        core.parse_cube(path)


def test_rejects_invalid_size(tmp_path):
    path = tmp_path / "size.cube"
    path.write_text("LUT_3D_SIZE 1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="between 2 and"):
        core.parse_cube(path)


def test_rejects_invalid_domain(tmp_path):
    path = write_cube(
        tmp_path / "domain.cube",
        domain_header="DOMAIN_MIN 1 0 0\nDOMAIN_MAX 1 1 1\n",
    )

    with pytest.raises(ValueError, match="DOMAIN_MAX"):
        core.parse_cube(path)


def test_rejects_non_finite_lut_values(tmp_path):
    path = write_cube(tmp_path / "non-finite.cube")
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("0.0 0.0 0.0", "1e999 0.0 0.0", 1), encoding="utf-8")

    with pytest.raises(ValueError, match="finite"):
        core.parse_cube(path)


def test_rejects_malformed_cube_rows(tmp_path):
    path = tmp_path / "malformed.cube"
    path.write_text("LUT_3D_SIZE 2\n0 0\n", encoding="utf-8")

    with pytest.raises(ValueError, match="three values"):
        core.parse_cube(path)


def test_blend_intensity_endpoints():
    original = np.array([[[0.1, 0.2, 0.3]]], dtype=np.float32)
    graded = np.array([[[0.8, 0.7, 0.6]]], dtype=np.float32)

    np.testing.assert_allclose(core.blend_intensity(graded, original, 0), original)
    np.testing.assert_allclose(core.blend_intensity(graded, original, 1), graded)


def test_rejects_invalid_image_shape(tmp_path):
    lut = core.parse_cube(write_cube(tmp_path / "identity.cube"))
    with pytest.raises(ValueError, match="height, width, 3"):
        core.apply_lut(np.zeros((3, 3), dtype=np.float32), lut)


def test_log_mode_is_not_misrepresented_as_supported(tmp_path):
    with pytest.raises(ValueError, match="camera-specific"):
        core.decode_raw(tmp_path / "unused.nef", colorspace="log")



def test_metadata_copy_keeps_rendered_color_space_and_orientation(tmp_path, monkeypatch):
    source = tmp_path / "source.nef"
    output = tmp_path / "rendered.jpg"
    captured = {}

    class Result:
        returncode = 0

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return Result()

    monkeypatch.setattr(core.subprocess, "run", fake_run)

    assert core.copy_metadata(source, output) is True
    command = captured["command"]
    assert "-EXIF:All" in command
    assert "-XMP:All" in command
    assert "-IPTC:All" in command
    assert "-all:all" not in command
    assert "-Orientation#=1" in command
    assert "-ColorSpace#=1" in command
    assert str(output) == command[-1]


def test_metadata_copy_reports_exiftool_failure(tmp_path, monkeypatch):
    class Result:
        returncode = 2

    monkeypatch.setattr(core.subprocess, "run", lambda *_args, **_kwargs: Result())

    assert core.copy_metadata(tmp_path / "source.nef", tmp_path / "rendered.jpg") is False
