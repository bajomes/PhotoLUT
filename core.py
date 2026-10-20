"""RAW decoding, .cube LUT parsing, and color processing helpers."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rawpy
from PIL import ImageCms

MAX_CUBE_BYTES = 10 * 1024 * 1024
MAX_LUT_SIZE = 128


@dataclass(frozen=True)
class CubeLUT:
    """A 3D .cube LUT, indexed in [blue, green, red] order."""

    size: int
    domain_min: np.ndarray
    domain_max: np.ndarray
    table: np.ndarray


def parse_cube(path: Path) -> CubeLUT:
    """Parse and validate a 3D .cube file before processing any image."""
    if path.stat().st_size > MAX_CUBE_BYTES:
        raise ValueError(f"{path.name}: LUT file exceeds the 10 MiB limit")

    size: int | None = None
    domain_min = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    domain_max = np.array([1.0, 1.0, 1.0], dtype=np.float32)
    values: list[float] = []
    data_started = False

    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for lineno, line in enumerate(stream, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            upper = line.upper()
            if upper.startswith("TITLE"):
                continue
            if upper.startswith("LUT_3D_SIZE"):
                parts = line.split()
                if data_started or size is not None or len(parts) != 2:
                    raise ValueError(f"{path.name}:{lineno}: invalid or duplicate LUT_3D_SIZE")
                try:
                    size = int(parts[1])
                except ValueError as exc:
                    raise ValueError(f"{path.name}:{lineno}: invalid LUT_3D_SIZE") from exc
                if not 2 <= size <= MAX_LUT_SIZE:
                    raise ValueError(
                        f"{path.name}:{lineno}: LUT_3D_SIZE must be between 2 and {MAX_LUT_SIZE}"
                    )
                continue
            if upper.startswith("DOMAIN_MIN") or upper.startswith("DOMAIN_MAX"):
                if data_started:
                    raise ValueError(f"{path.name}:{lineno}: domain declarations must precede LUT data")
                parts = line.split()
                if len(parts) != 4:
                    raise ValueError(f"{path.name}:{lineno}: expected three domain values")
                try:
                    domain = np.asarray([float(v) for v in parts[1:]], dtype=np.float32)
                except ValueError as exc:
                    raise ValueError(f"{path.name}:{lineno}: invalid domain value") from exc
                if not np.all(np.isfinite(domain)):
                    raise ValueError(f"{path.name}:{lineno}: domain values must be finite")
                if upper.startswith("DOMAIN_MIN"):
                    domain_min = domain
                else:
                    domain_max = domain
                continue

            if re.fullmatch(r"[0-9eE+.\- ]+", line):
                if size is None:
                    raise ValueError(f"{path.name}:{lineno}: LUT_3D_SIZE must precede LUT data")
                parts = line.split()
                if len(parts) != 3:
                    raise ValueError(f"{path.name}:{lineno}: each LUT entry must contain three values")
                expected = size**3 * 3
                if len(values) + 3 > expected:
                    raise ValueError(f"{path.name}:{lineno}: more values than declared LUT size")
                try:
                    values.extend(float(v) for v in parts)
                except ValueError as exc:
                    raise ValueError(f"{path.name}:{lineno}: invalid LUT value") from exc
                data_started = True
                continue

            raise ValueError(f"{path.name}:{lineno}: unsupported .cube directive: {line!r}")

    if size is None:
        raise ValueError(f"{path.name}: missing LUT_3D_SIZE")
    if not np.all(np.isfinite(domain_min)) or not np.all(np.isfinite(domain_max)):
        raise ValueError(f"{path.name}: domain values must be finite")
    if np.any(domain_max <= domain_min):
        raise ValueError(f"{path.name}: each DOMAIN_MAX value must exceed DOMAIN_MIN")
    expected = size**3 * 3
    if len(values) != expected:
        raise ValueError(
            f"{path.name}: found {len(values)} LUT values; expected exactly {expected}"
        )

    table_values = np.asarray(values, dtype=np.float32)
    if not np.all(np.isfinite(table_values)):
        raise ValueError(f"{path.name}: LUT values must all be finite")
    # .cube data changes red fastest, then green, then blue. The reshaped
    # dimensions are therefore [blue, green, red, output-channel].
    table = table_values.reshape(size, size, size, 3)
    return CubeLUT(size=size, domain_min=domain_min, domain_max=domain_max, table=table)


def apply_lut(image: np.ndarray, lut: CubeLUT) -> np.ndarray:
    """Apply a validated 3D LUT to an RGB float image in [0, 1]."""
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
    result = c0 + fb * (c1 - c0)
    return np.clip(result, 0.0, 1.0).astype(np.float32)


def decode_raw(path: Path, colorspace: str = "srgb") -> np.ndarray:
    """Decode RAW to predictable 16-bit sRGB. Camera-log modes need real transforms."""
    if colorspace != "srgb":
        raise ValueError(
            "Only sRGB / Rec.709 input is supported currently. Camera Log LUTs require "
            "a camera-specific transfer-function and gamut transform."
        )

    with rawpy.imread(str(path)) as raw:
        rgb16 = raw.postprocess(
            use_camera_wb=True,
            output_color=rawpy.ColorSpace.sRGB,
            output_bps=16,
            no_auto_bright=True,
            gamma=(2.222, 4.5),
            fbdd_noise_reduction=rawpy.FBDDNoiseReductionMode.Off,
        )
    return rgb16.astype(np.float32) / 65535.0


def blend_intensity(graded: np.ndarray, original: np.ndarray, intensity: float) -> np.ndarray:
    if not 0.0 <= intensity <= 1.0:
        raise ValueError("intensity must be between 0.0 and 1.0")
    if graded.shape != original.shape:
        raise ValueError("graded and original images must have identical shapes")
    return np.clip(graded * intensity + original * (1.0 - intensity), 0.0, 1.0).astype(np.float32)


def srgb_icc_profile() -> bytes:
    """Return a standard sRGB ICC profile for embedding in output files."""
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def copy_metadata(raw_path: Path, output_path: Path) -> bool:
    """Copy source metadata with ExifTool; return False if metadata copy fails."""
    try:
        result = subprocess.run(
            [
                "exiftool",
                "-TagsFromFile", str(raw_path),
                "-all:all",
                "-m",
                "-overwrite_original",
                str(output_path),
            ],
            capture_output=True,
            timeout=30,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
