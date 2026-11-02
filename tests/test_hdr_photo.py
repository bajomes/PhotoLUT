from pathlib import Path

import numpy as np
import pytest
import tifffile

import hdr_photo


def _write_rgb_tiff(path: Path, pixels: np.ndarray, **kwargs) -> None:
    tifffile.imwrite(path, pixels, photometric="rgb", **kwargs)


def test_srgb_round_trip():
    values = np.array([0.0, 0.003, 0.04, 0.18, 0.5, 1.0], dtype=np.float32)
    restored = hdr_photo._linear_to_srgb(hdr_photo._srgb_to_linear(values))
    np.testing.assert_allclose(restored, values, atol=1e-6)


def test_inverse_tone_map_preserves_shadows_and_expands_highlights():
    source = np.array([[[0.1, 0.1, 0.1], [0.9, 0.9, 0.9]]], dtype=np.float32)
    hdr = hdr_photo._make_hdr_intent(source, 4.0)
    np.testing.assert_allclose(hdr[0, 0], source[0, 0])
    assert np.all(hdr[0, 1] > source[0, 1])
    assert np.max(hdr) <= 4.0


@pytest.mark.parametrize("boost", [1.0, 0.5, 8.1, float("nan"), float("inf")])
def test_rejects_invalid_boost(boost):
    with pytest.raises(ValueError):
        hdr_photo._make_hdr_intent(np.zeros((1, 1, 3), dtype=np.float32), boost)


def test_loads_rgb_16bit_tiff(tmp_path: Path):
    source = tmp_path / "rgb.tiff"
    pixels = np.array([[[0, 32768, 65535]]], dtype=np.uint16)
    _write_rgb_tiff(source, pixels)
    rgb, icc = hdr_photo._load_tiff(source)
    assert rgb.shape == (1, 1, 3)
    assert icc is None
    np.testing.assert_allclose(rgb[0, 0], [0.0, 32768 / 65535, 1.0])


def test_rejects_non_rgb_tiff(tmp_path: Path):
    source = tmp_path / "gray.tiff"
    tifffile.imwrite(source, np.zeros((2, 2), dtype=np.uint16))
    with pytest.raises(ValueError, match="RGB photometric"):
        hdr_photo._load_tiff(source)


def test_rejects_transparent_rgba(tmp_path: Path):
    source = tmp_path / "alpha.tiff"
    pixels = np.full((2, 2, 4), 65535, dtype=np.uint16)
    pixels[0, 0, 3] = 0
    _write_rgb_tiff(source, pixels, extrasamples="unassalpha")
    with pytest.raises(ValueError, match="transparency"):
        hdr_photo._load_tiff(source)


def test_rejects_mult_page_tiff(tmp_path: Path):
    source = tmp_path / "multi.tiff"
    with tifffile.TiffWriter(source) as writer:
        writer.write(np.zeros((2, 2, 3), dtype=np.uint16), photometric="rgb")
        writer.write(np.zeros((2, 2, 3), dtype=np.uint16), photometric="rgb")
    with pytest.raises(ValueError, match="single-page"):
        hdr_photo._load_tiff(source)


def test_export_requires_encoder(tmp_path: Path, monkeypatch):
    source = tmp_path / "input.tiff"
    source.write_bytes(b"not a tiff")
    monkeypatch.setattr(hdr_photo.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="not installed"):
        hdr_photo.export_ultrahdr(source, tmp_path / "output.jpg")


def test_export_rejects_invalid_timeout_before_encoder(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(hdr_photo.shutil, "which", lambda _: "/usr/bin/uhdr_app")
    with pytest.raises(ValueError, match="timeout"):
        hdr_photo.export_ultrahdr(tmp_path / "missing.tiff", tmp_path / "out.jpg", timeout=0)



def test_encoder_uses_srgb_gamut_and_content_boost(tmp_path: Path, monkeypatch):
    source = tmp_path / "input.tiff"
    _write_rgb_tiff(source, np.full((2, 2, 3), 50000, dtype=np.uint16))
    monkeypatch.setattr(hdr_photo.shutil, "which", lambda _: "/usr/bin/ultrahdr_app")
    commands = []

    class Result:
        returncode = 0
        stderr = ""
        stdout = "gainmap metadata present"

    def fake_run(command, **kwargs):
        commands.append(command)
        if "-P" not in command:
            Path(command[command.index("-z") + 1]).write_bytes(b"fake jpeg")
        return Result()

    monkeypatch.setattr(hdr_photo.subprocess, "run", fake_run)
    result = hdr_photo.export_ultrahdr(source, tmp_path / "out.jpg", max_boost=3.5)
    encode = commands[0]
    assert encode[encode.index("-C") + 1] == "0"
    assert encode[encode.index("-c") + 1] == "0"
    assert encode[encode.index("-K") + 1] == "3.5"
    assert result["gain_map_verified"] is True
