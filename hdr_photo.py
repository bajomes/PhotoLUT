"""TIFF 16-bit to Ultra HDR JPEG export using Google's libultrahdr demo encoder.

The TIFF is treated as an SDR sRGB rendition. HDR highlights are reconstructed
with a conservative inverse-tone-map shoulder; they are not recovered source data.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image

MAX_TIFF_BYTES = 200 * 1024 * 1024
MAX_PIXELS = 80_000_000
DEFAULT_BOOST = 4.0


def _srgb_to_linear(values: np.ndarray) -> np.ndarray:
    return np.where(values <= 0.04045, values / 12.92,
                    ((values + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(values: np.ndarray) -> np.ndarray:
    values = np.clip(values, 0.0, 1.0)
    return np.where(values <= 0.0031308, values * 12.92,
                    1.055 * np.power(values, 1.0 / 2.4) - 0.055)


def _load_tiff(path: Path) -> tuple[np.ndarray, bytes | None]:
    if path.stat().st_size > MAX_TIFF_BYTES:
        raise ValueError("TIFF exceeds the 200 MiB limit")
    with tifffile.TiffFile(path) as tif:
        page = tif.pages[0]
        if len(tif.pages) != 1:
            raise ValueError("Only single-page TIFF files are supported")
        if page.bitspersample not in (16, (16, 16, 16), (16, 16, 16, 16)):
            raise ValueError("Input must be a 16-bit TIFF")
        pixels = page.asarray()
        icc = page.tags.get("InterColorProfile")
        icc_bytes = icc.value if icc is not None else None
    if pixels.ndim != 3 or pixels.shape[-1] not in (3, 4):
        raise ValueError("TIFF must contain RGB or RGBA pixels")
    if pixels.shape[0] * pixels.shape[1] > MAX_PIXELS:
        raise ValueError("TIFF exceeds the 80 megapixel limit")
    if pixels.dtype != np.uint16:
        raise ValueError("TIFF pixel data must be unsigned 16-bit")
    rgb = pixels[..., :3].astype(np.float32) / 65535.0
    return rgb, icc_bytes


def _make_hdr_intent(sdr_linear: np.ndarray, max_boost: float) -> np.ndarray:
    """Reconstruct a restrained highlight shoulder while leaving SDR base intact."""
    if not 1.0 < max_boost <= 8.0:
        raise ValueError("max_boost must be greater than 1 and no more than 8")
    luminance = (sdr_linear[..., 0] * 0.2126 +
                 sdr_linear[..., 1] * 0.7152 +
                 sdr_linear[..., 2] * 0.0722)
    shoulder = np.clip((luminance - 0.55) / 0.45, 0.0, 1.0)
    shoulder = shoulder * shoulder * (3.0 - 2.0 * shoulder)
    gain = 1.0 + (max_boost - 1.0) * shoulder
    return np.clip(sdr_linear * gain[..., None], 0.0, max_boost)


def export_ultrahdr(
    source: Path,
    destination: Path,
    *,
    encoder: str = "uhdr_app",
    quality: int = 100,
    max_boost: float = DEFAULT_BOOST,
    timeout: int = 180,
) -> dict:
    """Create a backward-compatible Ultra HDR JPEG and verify its gain map."""
    if not 1 <= quality <= 100:
        raise ValueError("quality must be between 1 and 100")
    executable = shutil.which(encoder)
    if executable is None:
        raise RuntimeError("Ultra HDR encoder 'uhdr_app' is not installed")
    sdr, icc = _load_tiff(source)
    height, width, _ = sdr.shape
    linear = _srgb_to_linear(sdr)
    hdr = _make_hdr_intent(linear, max_boost)
    rgba = np.empty((height, width, 4), dtype=np.float16)
    rgba[..., :3] = hdr.astype(np.float16)
    rgba[..., 3] = 1.0
    base = np.rint(_linear_to_srgb(linear) * 255.0).astype(np.uint8)

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="photolut-ultrahdr-") as tmp:
        tmpdir = Path(tmp)
        raw_path = tmpdir / "hdr-linear-rgba-f16.raw"
        base_path = tmpdir / "sdr-base.jpg"
        rgba.tofile(raw_path)
        Image.fromarray(base, "RGB").save(
            base_path, format="JPEG", quality=quality, subsampling=0,
            icc_profile=icc,
        )
        command = [
            executable, "-m", "0", "-p", str(raw_path), "-a", "4",
            "-t", "0", "-C", "1", "-i", str(base_path),
            "-w", str(width), "-h", str(height), "-q", str(quality),
            "-Q", str(quality), "-D", "1", "-z", str(destination),
        ]
        result = subprocess.run(command, capture_output=True, text=True,
                                timeout=timeout, check=False)
        if result.returncode != 0 or not destination.is_file():
            detail = (result.stderr or result.stdout or "encoder failed").strip()
            raise RuntimeError(f"Ultra HDR encoding failed: {detail[:500]}")
        probe = subprocess.run(
            [executable, "-m", "1", "-j", str(destination), "-P"],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
        probe_text = (probe.stdout or "") + (probe.stderr or "")
        if probe.returncode != 0 or "gainmap" not in probe_text.lower():
            destination.unlink(missing_ok=True)
            raise RuntimeError("Ultra HDR output failed gain-map metadata verification")
    return {
        "width": width,
        "height": height,
        "format": "JPEG Ultra HDR",
        "quality": quality,
        "max_content_boost": max_boost,
        "gain_map_verified": True,
        "sdr_fallback": True,
    }
