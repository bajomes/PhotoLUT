from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rawpy
import tifffile
from PIL import Image

MAX_JPEG_EXIF_BYTES = 65_500


@dataclass(frozen=True)
class CubeLUT:
    size: int
    domain_min: np.ndarray
    domain_max: np.ndarray
    table: np.ndarray


def parse_cube(path: Path) -> CubeLUT:
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
            raise ValueError(f"{path.name}:{lineno}: baris tak dikenal: {line!r}")

    if size is None:
        raise ValueError(f"{path.name}: tidak ada LUT_3D_SIZE")
    if not 2 <= size <= 256:
        raise ValueError(f"{path.name}: LUT_3D_SIZE {size} di luar rentang wajar (2-256)")
    expected = size**3 * 3
    if len(values) != expected:
        raise ValueError(f"{path.name}: jumlah nilai {len(values)}, diharapkan {expected}")
    if np.any(domain_max <= domain_min):
        raise ValueError(f"{path.name}: DOMAIN_MAX harus lebih besar dari DOMAIN_MIN")

    table = np.array(values, dtype=np.float32).reshape(size, size, size, 3)
    return CubeLUT(size=size, domain_min=domain_min, domain_max=domain_max, table=table)


def apply_lut(image: np.ndarray, lut: CubeLUT) -> np.ndarray:
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


def decode_raw(path: Path, colorspace: str = "srgb") -> np.ndarray:
    with rawpy.imread(str(path)) as raw:
        if colorspace == "log":
            rgb16 = raw.postprocess(
                use_camera_wb=True,
                output_color=rawpy.ColorSpace.sRGB,
                output_bps=16,
                no_auto_bright=False,
                gamma=(1.0, 1.0),
                fbdd_noise_reduction=rawpy.FBDDNoiseReductionMode.Off,
            )
            img = rgb16.astype(np.float32) / 65535.0
            return np.power(np.maximum(img, 1e-6), 1.0 / 2.4).astype(np.float32)
        else:
            rgb16 = raw.postprocess(
                use_camera_wb=True,
                output_color=rawpy.ColorSpace.sRGB,
                output_bps=16,
                no_auto_bright=False,
                fbdd_noise_reduction=rawpy.FBDDNoiseReductionMode.Off,
            )
            return rgb16.astype(np.float32) / 65535.0


def blend_intensity(graded: np.ndarray, original: np.ndarray, intensity: float) -> np.ndarray:
    return np.clip(graded * intensity + original * (1.0 - intensity), 0.0, 1.0).astype(np.float32)


def extract_exif(raw_path: Path) -> bytes | None:
    WHITELIST_IFD0 = {0x010F, 0x0110, 0x0112, 0x0132, 0x8769}
    WHITELIST_EXIF = {0x829A, 0x829D, 0x8827, 0x9000, 0x9003, 0x9004, 0x920A}

    try:
        with Image.open(raw_path) as im:
            original_exif = im.getexif()
            if not original_exif:
                return None

            new_exif = Image.Exif()

            for tag_id in WHITELIST_IFD0:
                if tag_id in original_exif and tag_id != 0x8769:
                    new_exif[tag_id] = original_exif[tag_id]

            try:
                exif_ifd = original_exif.get_ifd(0x8769)
                if exif_ifd:
                    new_exif_ifd = {}
                    for tag_id in WHITELIST_EXIF:
                        if tag_id in exif_ifd:
                            new_exif_ifd[tag_id] = exif_ifd[tag_id]
                    if new_exif_ifd:
                        new_exif[0x8769] = new_exif_ifd
            except Exception:
                pass

            blob = new_exif.tobytes()
            return blob if len(blob) <= MAX_JPEG_EXIF_BYTES else None
    except Exception:
        return None


def copy_exif_to_tiff(raw_path: Path, tiff_path: Path) -> None:
    try:
        subprocess.run(
            ["exiftool", "-TagsFromFile", str(raw_path), "-all:all",
             "-m", "-overwrite_original", str(tiff_path)],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except Exception:
        pass


def save_with_exif(image: Image.Image, path: Path,
                   exif: bytes | None = None, **save_kwargs) -> None:
    if exif:
        try:
            image.save(path, exif=exif, **save_kwargs)
            return
        except ValueError:
            pass
    image.save(path, **save_kwargs)