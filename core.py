"""Core processing: parse .cube LUT, decode RAW with color space options, apply LUT with intensity, preserve EXIF."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from io import BytesIO
import numpy as np
import piexif
import rawpy
import tifffile
from PIL import Image

ColorSpace = Literal["srgb", "adobergb", "slog3", "flog", "vlog"]


@dataclass(frozen=True)
class CubeLUT:
    """Parsed 3D LUT from .cube file."""
    size: int
    domain_min: np.ndarray  # shape (3,)
    domain_max: np.ndarray  # shape (3,)
    table: np.ndarray       # shape (size, size, size, 3), index [b][g][r]


def parse_cube(path: Path) -> CubeLUT:
    """Parse 3D .cube file. Fails fast on malformed files."""
    size: int | None = None
    domain_min = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    domain_max = np.array([1.0, 1.0, 1.0], dtype=np.float32)
    values: list[float] = []

    with path.open("r", encoding="utf-8", errors="replace") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#") or line.upper().startswith("TITLE"):
                continue
            if line.upper().startswith("LUT_3D_SIZE"):
                size = int(line.split()[1])
                continue
            if line.upper().startswith("DOMAIN_MIN"):
                domain_min = np.array(line.split()[1:4], dtype=np.float32)
                continue
            if line.upper().startswith("DOMAIN_MAX"):
                domain_max = np.array(line.split()[1:4], dtype=np.float32)
                continue
            if re.match(r"^[0-9eE+.\- ]+$", line):
                values.extend(float(v) for v in line.split())
                continue
            raise ValueError(f"{path.name}:{lineno}: unknown line: {line!r}")

    if size is None:
        raise ValueError(f"{path.name}: missing LUT_3D_SIZE")
    if not 2 <= size <= 256:
        raise ValueError(f"{path.name}: LUT_3D_SIZE {size} out of range (2-256)")
    expected = size**3 * 3
    if len(values) != expected:
        raise ValueError(f"{path.name}: {len(values)} values, expected {expected}")
    if np.any(domain_max <= domain_min):
        raise ValueError(f"{path.name}: DOMAIN_MAX must be greater than DOMAIN_MIN")

    table = np.array(values, dtype=np.float32).reshape(size, size, size, 3)
    return CubeLUT(size=size, domain_min=domain_min, domain_max=domain_max, table=table)


def apply_lut(image: np.ndarray, lut: CubeLUT) -> np.ndarray:
    """Apply 3D LUT with trilinear interpolation. image: float32 [0,1], shape (H,W,3)."""
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


def _slog3_to_linear(x: np.ndarray) -> np.ndarray:
    """Convert S-Log3 to linear."""
    return np.where(
        x >= 0.01125000 * (171.415 + 928.35) / 928.35,
        (np.power(10, (x - 0.01125000 * (171.415 + 928.35) / 928.35) / 261.5) - 0.01125000) * (171.415 + 928.35) / (10 - 0.01125000),
        (x - 0.030001222851889303) / 5.555556
    )


def _linear_to_slog3(x: np.ndarray) -> np.ndarray:
    """Convert linear to S-Log3."""
    return np.where(
        x >= 0.01125000,
        0.01125000 * (171.415 + 928.35) / 928.35 + 261.5 * np.log10(x * (10 - 0.01125000) / (171.415 + 928.35) + 0.01125000),
        x * 5.555556 + 0.030001222851889303
    )


def _flog_to_linear(x: np.ndarray) -> np.ndarray:
    """Convert F-Log to linear."""
    return np.where(
        x >= 0.4127397,
        np.power(10, (x - 0.555554) / 0.571387) * 0.18 - 0.000015,
        (x - 0.092864) / 5.393014
    )


def _linear_to_flog(x: np.ndarray) -> np.ndarray:
    """Convert linear to F-Log."""
    return np.where(
        x >= 0.000015,
        0.571387 * np.log10((x + 0.000015) / 0.18) + 0.555554,
        x * 5.393014 + 0.092864
    )


def _vlog_to_linear(x: np.ndarray) -> np.ndarray:
    """Convert V-Log to linear."""
    return np.where(
        x >= 0.181,
        np.power(10, (x - 0.396) / 0.538) * 0.18 - 0.000015,
        (x - 0.125) / 5.555556
    )


def _linear_to_vlog(x: np.ndarray) -> np.ndarray:
    """Convert linear to V-Log."""
    return np.where(
        x >= 0.000015,
        0.538 * np.log10((x + 0.000015) / 0.18) + 0.396,
        x * 5.555556 + 0.125
    )


def decode_raw(path: Path, color_space: ColorSpace = "srgb") -> np.ndarray:
    """Decode RAW to float32 [0,1] in specified color space."""
    with rawpy.imread(str(path)) as raw:
        # For Rec.709/sRGB and Adobe RGB, use rawpy's built-in color spaces
        if color_space == "srgb":
            rgb16 = raw.postprocess(
                use_camera_wb=True,
                output_color=rawpy.ColorSpace.sRGB,
                output_bps=16,
                no_auto_bright=False,
                fbdd_noise_reduction=rawpy.FBDDNoiseReductionMode.Off,
            )
            return rgb16.astype(np.float32) / 65535.0
        elif color_space == "adobergb":
            rgb16 = raw.postprocess(
                use_camera_wb=True,
                output_color=rawpy.ColorSpace.Adobe,
                output_bps=16,
                no_auto_bright=False,
                fbdd_noise_reduction=rawpy.FBDDNoiseReductionMode.Off,
            )
            return rgb16.astype(np.float32) / 65535.0
        else:
            # For Log spaces, decode to linear first, then apply log curve
            rgb16 = raw.postprocess(
                use_camera_wb=True,
                output_color=rawpy.ColorSpace.sRGB,
                output_bps=16,
                no_auto_bright=False,
                gamma=(1.0, 1.0),  # Linear output
                fbdd_noise_reduction=rawpy.FBDDNoiseReductionMode.Off,
            )
            linear = rgb16.astype(np.float32) / 65535.0
            
            if color_space == "slog3":
                return _linear_to_slog3(linear)
            elif color_space == "flog":
                return _linear_to_flog(linear)
            elif color_space == "vlog":
                return _linear_to_vlog(linear)
            else:
                raise ValueError(f"Unsupported color space: {color_space}")


def extract_exif(path: Path) -> dict | None:
    """Extract EXIF from the RAW's embedded JPEG preview; fall back to camera make/model."""
    try:
        with rawpy.imread(str(path)) as raw:
            exif_dict: dict | None = None
            try:
                thumb = raw.extract_thumb()
                if thumb.format == rawpy.ThumbFormat.JPEG:
                    preview = Image.open(BytesIO(thumb.data))
                    blob = preview.info.get("exif")
                    if blob:
                        exif_dict = piexif.load(blob)
            except rawpy.LibRawNoThumbnailError:
                pass
            if exif_dict is None:
                exif_dict = {"0th": {}, "Exif": {}, "1st": {}, "GPS": {}, "thumbnail": None}
            if raw.camera_make:
                exif_dict["0th"][piexif.ImageIFD.Make] = raw.camera_make.encode("utf-8", "replace")
            if raw.camera_model:
                exif_dict["0th"][piexif.ImageIFD.Model] = raw.camera_model.encode("utf-8", "replace")
            return exif_dict
    except Exception:
        return None


def save_with_exif(image: Image.Image, path: Path, exif_dict: dict | None) -> None:
    """Save JPEG; embed EXIF if present, with dimensions corrected to output size."""
    if exif_dict is None:
        image.save(path, quality=95)
        return
    exif_dict["Exif"][piexif.ExifIFD.PixelXDimension] = image.width
    exif_dict["Exif"][piexif.ExifIFD.PixelYDimension] = image.height
    image.save(path, quality=95, exif=piexif.dump(exif_dict))


def process_photo(raw_path: Path, cube_path: Path, out_dir: Path, 
                  color_space: ColorSpace = "srgb", intensity: float = 1.0,
                  preview_max_side: int = 1600) -> dict[str, Path]:
    """Full pipeline: RAW + .cube → TIFF 16-bit, JPEG 8-bit with EXIF, and previews."""
    lut = parse_cube(cube_path)
    image = decode_raw(raw_path, color_space)
    
    # Apply LUT with intensity mixing
    if intensity >= 1.0:
        graded = apply_lut(image, lut)
    elif intensity <= 0.0:
        graded = image
    else:
        graded_lut = apply_lut(image, lut)
        graded = image * (1 - intensity) + graded_lut * intensity
        graded = np.clip(graded, 0.0, 1.0).astype(np.float32)

    # Extract EXIF from original RAW
    exif_dict = extract_exif(raw_path)

    out_dir.mkdir(parents=True, exist_ok=True)
    stem = raw_path.stem
    paths: dict[str, Path] = {}

    # Save TIFF 16-bit
    tiff16 = (graded * 65535.0).round().astype(np.uint16)
    paths["tiff"] = out_dir / f"{stem}_lut.tiff"
    tifffile.imwrite(paths["tiff"], tiff16, photometric="rgb", compression="deflate")

    # Save JPEG 8-bit with EXIF
    jpeg8 = (graded * 255.0).round().astype(np.uint8)
    jpeg_img = Image.fromarray(jpeg8, "RGB")
    paths["jpeg"] = out_dir / f"{stem}_lut.jpg"
    save_with_exif(jpeg_img, paths["jpeg"], exif_dict, raw_path, "jpeg")

    # Generate previews
    before8 = (image * 255.0).round().astype(np.uint8)
    before_img = Image.fromarray(before8, "RGB")
    after_img = Image.fromarray(jpeg8, "RGB")
    
    scale = min(1.0, preview_max_side / max(before_img.size))
    if scale < 1.0:
        size = (max(1, int(before_img.width * scale)),
                max(1, int(before_img.height * scale)))
        before_img = before_img.resize(size, Image.LANCZOS)
        after_img = after_img.resize(size, Image.LANCZOS)
    
    paths["preview_before"] = out_dir / "preview_before.jpg"
    paths["preview_after"] = out_dir / "preview_after.jpg"
    before_img.save(paths["preview_before"], quality=88)
    after_img.save(paths["preview_after"], quality=88)
    
    return paths