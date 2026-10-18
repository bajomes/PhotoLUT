"""Inti pemrosesan: parse LUT .cube, decode RAW, terapkan LUT, simpan hasil."""
from __future__ import annotations

import tifffile
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rawpy
from PIL import Image


@dataclass(frozen=True)
class CubeLUT:
    """LUT 3D hasil parse berkas .cube."""
    size: int
    domain_min: np.ndarray  # shape (3,)
    domain_max: np.ndarray  # shape (3,)
    table: np.ndarray       # shape (size, size, size, 3), indeks [b][g][r]


def parse_cube(path: Path) -> CubeLUT:
    """Parse berkas .cube 3D. Gagal cepat pada berkas cacat."""
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

    # Urutan .cube: R berubah paling cepat → reshape langsung memberi indeks [b][g][r]
    table = np.array(values, dtype=np.float32).reshape(size, size, size, 3)
    return CubeLUT(size=size, domain_min=domain_min, domain_max=domain_max, table=table)


def apply_lut(image: np.ndarray, lut: CubeLUT) -> np.ndarray:
    """Terapkan LUT 3D dengan interpolasi trilinear. image: float32 [0,1], shape (H,W,3)."""
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


def decode_raw(path: Path) -> np.ndarray:
    """Decode RAW → sRGB float32 [0,1], white balance kamera, gamma sRGB (default rawpy)."""
    with rawpy.imread(str(path)) as raw:
        rgb16 = raw.postprocess(
            use_camera_wb=True,
            output_color=rawpy.ColorSpace.sRGB,
            output_bps=16,
            no_auto_bright=False,
            fbdd_noise_reduction=rawpy.FBDDNoiseReductionMode.Off,
        )
    return rgb16.astype(np.float32) / 65535.0


def process_photo(raw_path: Path, cube_path: Path, out_dir: Path,
                  preview_max_side: int = 1600) -> dict[str, Path]:
    """Alur penuh: RAW + .cube → TIFF 16-bit, JPEG 8-bit, dan dua JPEG preview."""
    lut = parse_cube(cube_path)
    image = decode_raw(raw_path)
    graded = apply_lut(image, lut)

    out_dir.mkdir(parents=True, exist_ok=True)
    stem = raw_path.stem
    paths: dict[str, Path] = {}

    tiff16 = (graded * 65535.0).round().astype(np.uint16)
    paths["tiff"] = out_dir / f"{stem}_lut.tiff"
    tifffile.imwrite(paths["tiff"], tiff16, photometric="rgb", compression="deflate")

    jpeg8 = (graded * 255.0).round().astype(np.uint8)
    paths["jpeg"] = out_dir / f"{stem}_lut.jpg"
    Image.fromarray(jpeg8, "RGB").save(paths["jpeg"], quality=95)

    before8 = (image * 255.0).round().astype(np.uint8)
    before_img = Image.fromarray(before8, "RGB")
    after_img = Image.fromarray(jpeg8, "RGB")
    scale = min(1.0, preview_max_side / max(before_img.size))
    if scale < 1.0:
        size = (max(1, int(before_img.width * scale)), max(1, int(before_img.height * scale)))
        before_img = before_img.resize(size, Image.LANCZOS)
        after_img = after_img.resize(size, Image.LANCZOS)
    paths["preview_before"] = out_dir / "preview_before.jpg"
    paths["preview_after"] = out_dir / "preview_after.jpg"
    before_img.save(paths["preview_before"], quality=88)
    after_img.save(paths["preview_after"], quality=88)
    return paths