from pathlib import Path

import numpy as np
import pytest
import tifffile
from PIL import ImageCms

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



def test_accepts_real_srgb_icc_profile():
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
    assert hdr_photo._is_srgb_profile(profile.tobytes())


def test_rejects_non_rgb_icc_profile():
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("LAB"))
    with pytest.raises(ValueError, match="ICC profile"):
        hdr_photo._is_srgb_profile(profile.tobytes())

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
        stdout = "Ultra HDR Image: Yes\nGainMap Metadata:\n--maxContentBoost 2.8\n"

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
    assert encode[encode.index("-t") + 1] == "0"
    assert encode[encode.index("-a") + 1] == "4"
    assert encode[encode.index("-K") + 1] == "3.5"
    assert result["max_content_boost"] == pytest.approx(2.8)
    assert result["gain_map_verified"] is True



def test_encoder_timeout_removes_partial_output(tmp_path: Path, monkeypatch):
    source = tmp_path / "input.tiff"
    _write_rgb_tiff(source, np.full((2, 2, 3), 50000, dtype=np.uint16))
    destination = tmp_path / "out.jpg"
    destination.write_bytes(b"stale partial")
    monkeypatch.setattr(hdr_photo.shutil, "which", lambda _: "/usr/bin/ultrahdr_app")

    def timeout(*_args, **_kwargs):
        raise hdr_photo.subprocess.TimeoutExpired("ultrahdr_app", 180)

    monkeypatch.setattr(hdr_photo.subprocess, "run", timeout)
    with pytest.raises(RuntimeError, match="timed out"):
        hdr_photo.export_ultrahdr(source, destination)
    assert not destination.exists()


def test_rejects_tiff_over_8_megapixels(tmp_path: Path):
    source = tmp_path / "too-large.tiff"
    # A tiny on-disk tiled TIFF with oversized dimensions is unnecessary here;
    # exercise the public dimension guard before decoding pixel data.
    class FakePage:
        bitspersample = 16
        photometric = 2
        planarconfig = 1
        sampleformat = 1
        samplesperpixel = 3
        imagewidth = 3000
        imagelength = 3000
        tags = {}

        def asarray(self):
            raise AssertionError("oversized TIFF must be rejected before decoding")

    class FakeTiff:
        pages = [FakePage()]

        def __enter__(self): return self
        def __exit__(self, *_args): return False

    source.write_bytes(b"tiff")
    import tifffile
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(tifffile, "TiffFile", lambda _path: FakeTiff())
    try:
        with pytest.raises(ValueError, match="8 megapixel"):
            hdr_photo._load_tiff(source)
    finally:
        monkeypatch.undo()


def test_encoder_rejects_gainmap_boost_mismatch(tmp_path: Path, monkeypatch):
    source = tmp_path / "input.tiff"
    _write_rgb_tiff(source, np.full((2, 2, 3), 50000, dtype=np.uint16))
    destination = tmp_path / "out.jpg"
    monkeypatch.setattr(hdr_photo.shutil, "which", lambda _: "/usr/bin/ultrahdr_app")

    class Result:
        returncode = 0
        stderr = ""
        stdout = "Ultra HDR Image: Yes\nGainMap Metadata:\n--maxContentBoost 4.0\n"

    def fake_run(command, **kwargs):
        if "-P" not in command:
            Path(command[command.index("-z") + 1]).write_bytes(b"fake jpeg")
        return Result()

    monkeypatch.setattr(hdr_photo.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="exceeds the requested maximum"):
        hdr_photo.export_ultrahdr(source, destination, max_boost=3.5)
    assert not destination.exists()


def test_loads_big_endian_rgb_16bit_tiff(tmp_path: Path):
    source = tmp_path / "big-endian.tiff"
    pixels = np.array([[[1000, 32000, 65000]]], dtype=">u2")
    tifffile.imwrite(source, pixels, photometric="rgb", byteorder=">")
    rgb, _ = hdr_photo._load_tiff(source)
    np.testing.assert_allclose(rgb[0, 0], pixels[0, 0].astype(np.float32) / 65535.0)


def test_applies_tiff_orientation_before_export(tmp_path: Path):
    source = tmp_path / "rotated.tiff"
    pixels = np.arange(18, dtype=np.uint16).reshape(2, 3, 3) * 3000
    tifffile.imwrite(
        source, pixels, photometric="rgb",
        extratags=[(274, "H", 1, 6, False)],
    )
    rgb, _ = hdr_photo._load_tiff(source)
    expected = np.rot90(pixels, k=3, axes=(0, 1)).astype(np.float32) / 65535.0
    assert rgb.shape == (3, 2, 3)
    np.testing.assert_allclose(rgb, expected)


def test_rejects_unreadable_tiff(tmp_path: Path):
    source = tmp_path / "invalid.tiff"
    source.write_bytes(b"not a TIFF file")
    with pytest.raises(ValueError, match="readable TIFF"):
        hdr_photo._load_tiff(source)
