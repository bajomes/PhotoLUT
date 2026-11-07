from pathlib import Path

import numpy as np
import pytest
import tifffile
from PIL import Image, ImageCms

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
            base_path = Path(command[command.index("-i") + 1])
            with Image.open(base_path) as base_image:
                assert base_image.info.get("icc_profile"), "SDR JPEG base must embed an sRGB ICC profile"
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


@pytest.mark.parametrize(
    ("orientation", "expected"),
    [
        (1, [[0, 1, 2], [3, 4, 5]]),
        (2, [[2, 1, 0], [5, 4, 3]]),
        (3, [[5, 4, 3], [2, 1, 0]]),
        (4, [[3, 4, 5], [0, 1, 2]]),
        (5, [[0, 3], [1, 4], [2, 5]]),
        (6, [[3, 0], [4, 1], [5, 2]]),
        (7, [[5, 2], [4, 1], [3, 0]]),
        (8, [[2, 5], [1, 4], [0, 3]]),
    ],
)
def test_applies_all_tiff_orientations_before_export(
    tmp_path: Path, orientation: int, expected: list[list[int]]
):
    source = tmp_path / f"orientation-{orientation}.tiff"
    pixels = np.repeat(
        np.arange(6, dtype=np.uint16).reshape(2, 3, 1) * 10000,
        3,
        axis=2,
    )
    tifffile.imwrite(
        source, pixels, photometric="rgb",
        extratags=[(274, "H", 1, orientation, False)],
    )
    rgb, _ = hdr_photo._load_tiff(source)
    expected_rgb = np.repeat(
        np.asarray(expected, dtype=np.float32)[..., None] * (10000 / 65535.0),
        3,
        axis=2,
    )
    assert rgb.shape == expected_rgb.shape
    np.testing.assert_allclose(rgb, expected_rgb)


def test_rejects_invalid_tiff_orientation(tmp_path: Path):
    source = tmp_path / "invalid-orientation.tiff"
    pixels = np.zeros((2, 3, 3), dtype=np.uint16)
    tifffile.imwrite(
        source, pixels, photometric="rgb",
        extratags=[(274, "H", 1, 9, False)],
    )
    with pytest.raises(ValueError, match="orientation"):
        hdr_photo._load_tiff(source)


def test_rejects_unreadable_tiff(tmp_path: Path):
    source = tmp_path / "invalid.tiff"
    source.write_bytes(b"not a TIFF file")
    with pytest.raises(ValueError, match="readable TIFF"):
        hdr_photo._load_tiff(source)

def test_accepts_fully_opaque_rgba_tiff(tmp_path: Path):
    source = tmp_path / "opaque-rgba.tiff"
    pixels = np.full((2, 3, 4), 65535, dtype=np.uint16)
    pixels[..., 0] = 12000
    tifffile.imwrite(source, pixels, photometric="rgb", extrasamples="unassalpha")
    rgb, icc = hdr_photo._load_tiff(source)
    assert rgb.shape == (2, 3, 3)
    assert icc is None
    np.testing.assert_allclose(rgb[..., 0], 12000 / 65535.0)


def test_rejects_rgba_tiff_without_declared_alpha_type(tmp_path: Path, monkeypatch):
    source = tmp_path / "rgba-without-extra-samples.tiff"
    source.write_bytes(b"fixture")

    class FakePage:
        bitspersample = 16
        photometric = 2
        planarconfig = 1
        sampleformat = 1
        samplesperpixel = 4
        imagewidth = 3
        imagelength = 2
        tags = {}

    class FakeTiff:
        pages = [FakePage()]

        def __enter__(self): return self
        def __exit__(self, *_args): return False

    monkeypatch.setattr(tifffile, "TiffFile", lambda _path: FakeTiff())
    with pytest.raises(ValueError, match="ExtraSamples"):
        hdr_photo._load_tiff(source)


def test_rejects_eight_bit_rgb_tiff(tmp_path: Path):
    source = tmp_path / "rgb8.tiff"
    tifffile.imwrite(source, np.zeros((2, 2, 3), dtype=np.uint8), photometric="rgb")
    with pytest.raises(ValueError, match="16-bit"):
        hdr_photo._load_tiff(source)


def test_rejects_planar_separate_rgb_tiff(tmp_path: Path):
    source = tmp_path / "planar.tiff"
    pixels = np.zeros((3, 2, 2), dtype=np.uint16)
    tifffile.imwrite(source, pixels, photometric="rgb", planarconfig="separate")
    with pytest.raises(ValueError, match="Planar-separate"):
        hdr_photo._load_tiff(source)


@pytest.mark.parametrize(
    "probe_result",
    [
        (1, "Ultra HDR Image: Yes\\nGainMap Metadata:\\n--maxContentBoost 2.0\\n"),
        (0, "Ultra HDR Image: No\\n"),
        (0, "Ultra HDR Image: Yes\\nGainMap Metadata missing\\n"),
        (0, "Ultra HDR Image: Yes\\nGainMap Metadata:\\n"),
    ],
)
def test_encoder_rejects_unverified_gainmap_and_removes_output(
    tmp_path: Path, monkeypatch, probe_result
):
    source = tmp_path / "input.tiff"
    _write_rgb_tiff(source, np.full((2, 2, 3), 50000, dtype=np.uint16))
    destination = tmp_path / "out.jpg"
    monkeypatch.setattr(hdr_photo.shutil, "which", lambda _: "/usr/bin/ultrahdr_app")
    calls = 0

    class Result:
        def __init__(self, returncode, stdout):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""

    def fake_run(command, **_kwargs):
        nonlocal calls
        calls += 1
        if "-P" not in command:
            Path(command[command.index("-z") + 1]).write_bytes(b"partial jpeg")
            return Result(0, "encoded")
        return Result(*probe_result)

    monkeypatch.setattr(hdr_photo.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="gain-map metadata verification"):
        hdr_photo.export_ultrahdr(source, destination)
    assert calls == 2
    assert not destination.exists()

