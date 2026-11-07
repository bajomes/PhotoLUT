#!/usr/bin/env python3
"""Measure one complete PhotoLUT RAW → LUT → JPEG/TIFF export on Linux.

Run from the repository root:
  python scripts/benchmark_photo.py /path/to/photo.NEF /path/to/look.cube

The script uses the production decode, LUT, intensity and output functions. It
reports wall-clock stage times and process peak RSS; run it in a fresh process
for each sample so ru_maxrss is meaningful.
"""
from __future__ import annotations

import argparse
import json
import platform
import sys

try:
    import resource
except ImportError:  # pragma: no cover - only available on Unix
    resource = None
import tempfile
import time
from pathlib import Path

import numpy as np
import PIL
import rawpy
import tifffile

import app
import core


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path, help="RAW photograph to benchmark")
    parser.add_argument("lut", type=Path, help="3D .cube LUT")
    parser.add_argument("--intensity", type=float, default=1.0, help="LUT intensity from 0 to 1")
    args = parser.parse_args()

    if sys.platform != "linux" or resource is None:
        parser.error("Peak-RSS measurement is defined for Linux only.")
    if not args.raw.is_file():
        parser.error(f"RAW file does not exist: {args.raw}")
    if not args.lut.is_file():
        parser.error(f"LUT file does not exist: {args.lut}")
    if not 0.0 <= args.intensity <= 1.0:
        parser.error("--intensity must be between 0 and 1")

    started = time.perf_counter()
    stage_times: dict[str, float] = {}

    stage = time.perf_counter()
    lut = core.parse_cube(args.lut)
    stage_times["lut_parse_seconds"] = time.perf_counter() - stage

    stage = time.perf_counter()
    image = core.decode_raw(args.raw, colorspace="srgb")
    stage_times["raw_decode_seconds"] = time.perf_counter() - stage

    stage = time.perf_counter()
    graded = core.apply_lut(image, lut)
    if args.intensity < 1.0:
        graded = core.blend_intensity(graded, image, args.intensity)
    stage_times["lut_and_blend_seconds"] = time.perf_counter() - stage

    stage = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="photolut-benchmark-") as directory:
        outputs, metadata_preserved = app._save_outputs(
            graded, image, Path(directory), args.raw.stem, 0, args.raw
        )
        output_sizes = {
            key: path.stat().st_size for key, path in outputs.items()
        }
    stage_times["export_seconds"] = time.perf_counter() - stage

    peak_rss_bytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    height, width, channels = image.shape
    report = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "rawpy": rawpy.__version__,
        "pillow": PIL.__version__,
        "tifffile": tifffile.__version__,
        "raw_file": args.raw.name,
        "raw_file_bytes": args.raw.stat().st_size,
        "lut_file": args.lut.name,
        "lut_size": lut.size,
        "intensity": args.intensity,
        "image_width": width,
        "image_height": height,
        "channels": channels,
        "image_float32_bytes": image.nbytes,
        "peak_rss_bytes": peak_rss_bytes,
        "peak_rss_mib": round(peak_rss_bytes / (1024 ** 2), 2),
        "metadata_preserved": metadata_preserved,
        "output_sizes_bytes": output_sizes,
        **stage_times,
        "total_seconds": time.perf_counter() - started,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
