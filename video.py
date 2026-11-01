"""Video metadata inspection for the HLG HDR workflow.

This module deliberately inspects source metadata only. It does not decode,
grade, tone-map, or re-encode video; those operations belong to later stages
with explicit color-management tests.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile

router = APIRouter(prefix="/api/video", tags=["video"])
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv"}
MAX_VIDEO_BYTES = 512 * 1024 * 1024
FFPROBE_TIMEOUT_SECONDS = 20


def _bit_depth(stream: dict[str, Any]) -> int | None:
    raw = stream.get("bits_per_raw_sample")
    try:
        if raw not in (None, "", "0", 0):
            return int(raw)
    except (TypeError, ValueError):
        pass

    pixel_format = str(stream.get("pix_fmt") or "").lower()
    for depth in (16, 14, 12, 10, 9):
        if f"{depth}le" in pixel_format or f"{depth}be" in pixel_format:
            return depth
    if pixel_format.endswith("p"):
        return 8
    return None


def _parse_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def normalize_probe_data(payload: dict[str, Any]) -> dict[str, Any]:
    streams = payload.get("streams") or []
    stream = next((item for item in streams if item.get("codec_type") == "video"), None)
    if not stream:
        raise ValueError("No video stream was found in the uploaded file.")

    transfer = str(stream.get("color_transfer") or "unknown").lower()
    primaries = str(stream.get("color_primaries") or "unknown").lower()
    matrix = str(stream.get("color_space") or "unknown").lower()
    depth = _bit_depth(stream)
    is_hlg = transfer == "arib-std-b67"
    hlg_metadata_complete = (
        is_hlg and primaries == "bt2020"
        and matrix in {"bt2020nc", "bt2020_ncl"}
        and depth is not None and depth >= 10
    )

    warnings: list[str] = []
    if transfer == "unknown" or primaries == "unknown" or matrix == "unknown":
        warnings.append("Some color metadata is missing; confirm the source profile before grading.")
    if is_hlg and not hlg_metadata_complete:
        warnings.append("HLG transfer metadata was detected, but the BT.2020 matrix/primaries or 10-bit depth could not be confirmed.")
    if not is_hlg:
        warnings.append("The file is not tagged with the HLG transfer function; it will not be treated as HLG.")

    fmt = payload.get("format") or {}
    return {
        "filename": None,
        "codec": stream.get("codec_name"),
        "codec_profile": stream.get("profile"),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "pixel_format": stream.get("pix_fmt"),
        "bit_depth": depth,
        "frame_rate": stream.get("avg_frame_rate") or stream.get("r_frame_rate"),
        "duration_seconds": _parse_float(fmt.get("duration")),
        "container": fmt.get("format_name"),
        "color_transfer": transfer,
        "color_primaries": primaries,
        "color_matrix": matrix,
        "color_range": stream.get("color_range") or "unknown",
        "is_hlg": is_hlg,
        "hlg_metadata_complete": hlg_metadata_complete,
        "warnings": warnings,
    }


def inspect_video(path: Path) -> dict[str, Any]:
    """Run ffprobe without a shell and return normalized video/color metadata."""
    executable = shutil.which("ffprobe")
    if not executable:
        raise RuntimeError("ffprobe is not installed. Install FFmpeg to inspect video files.")

    command = [
        executable, "-v", "error", "-select_streams", "v:0",
        "-show_entries",
        "stream=codec_type,codec_name,profile,width,height,pix_fmt,bits_per_raw_sample,"
        "avg_frame_rate,r_frame_rate,color_range,color_space,color_transfer,color_primaries:"
        "format=duration,format_name",
        "-of", "json", str(path),
    ]
    try:
        completed = subprocess.run(
            command, check=True, capture_output=True, text=True,
            timeout=FFPROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Video metadata inspection timed out.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip()
        raise ValueError(detail[:300] or "FFprobe could not read this video.") from exc

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("FFprobe returned invalid metadata.") from exc
    return normalize_probe_data(payload)


@router.post("/inspect")
async def inspect_uploaded_video(video_file: UploadFile) -> dict[str, Any]:
    """Inspect an uploaded video and identify HLG metadata without re-encoding it."""
    filename = video_file.filename or "video"
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_VIDEO_EXTENSIONS:
        raise HTTPException(400, "Supported video formats: MP4, MOV, M4V, and MKV.")

    try:
        with tempfile.TemporaryDirectory(prefix="photolut-video-inspect-") as temp_dir:
            path = Path(temp_dir) / f"input{extension}"
            size = 0
            with path.open("wb") as output:
                while chunk := await video_file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_VIDEO_BYTES:
                        raise HTTPException(413, "Video exceeds the 512 MiB inspection limit.")
                    output.write(chunk)
            if size == 0:
                raise HTTPException(400, "The uploaded video is empty.")
            try:
                metadata = await asyncio.to_thread(inspect_video, path)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            except RuntimeError as exc:
                raise HTTPException(503, str(exc)) from exc
            metadata["filename"] = Path(filename.replace(chr(92), "/")).name
            return metadata
    finally:
        await video_file.close()
