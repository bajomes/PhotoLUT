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

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

import core

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
    is_pq = transfer in {"smpte2084", "smpte-st-2084"}
    is_hdr = is_hlg or is_pq
    hdr_metadata_complete = (
        is_hdr and primaries == "bt2020"
        and matrix in {"bt2020nc", "bt2020_ncl"}
        and depth is not None and depth >= 10
    )
    side_data = stream.get("side_data_list") or []
    dolby_vision = next((item for item in side_data
                         if "dovi" in str(item.get("side_data_type", "")).lower()
                         or "dolby vision" in str(item.get("side_data_type", "")).lower()), None)
    dv_profile = (dolby_vision or {}).get("dv_profile")
    try:
        fps_num, fps_den = str(stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/1").split("/", 1)
        fps = float(fps_num) / float(fps_den) if float(fps_den) else None
    except (TypeError, ValueError, ZeroDivisionError):
        fps = None
    width, height = stream.get("width"), stream.get("height")
    is_4k30 = bool(width and height and width >= 3840 and height >= 2160 and fps is not None and abs(fps - 30) <= 0.1)
    hdr_format = ("Dolby Vision" if dolby_vision else
                  "HDR10 / PQ" if is_pq else "HLG" if is_hlg else
                  "SDR / BT.709" if transfer == "bt709" else "Unknown")

    warnings: list[str] = []
    if transfer == "unknown" or primaries == "unknown" or matrix == "unknown":
        warnings.append("Some color metadata is missing; confirm the source profile before grading.")
    if is_hdr and not hdr_metadata_complete:
        warnings.append("An HDR transfer function was detected, but BT.2020 matrix/primaries or at least 10-bit depth could not be confirmed.")
    if not is_hdr:
        warnings.append("The file is not tagged as HLG or PQ HDR; it will not be treated as an HDR source.")
    if dolby_vision and not is_pq:
        warnings.append("Dolby Vision side data was found; verify the profile and base-layer compatibility before delivery.")
    if not is_4k30:
        warnings.append("The source is not confirmed as at least 3840×2160 at 30 fps; PhotoLUT will not force an upscale or frame-rate conversion during inspection.")

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
        "is_pq": is_pq,
        "is_hdr": is_hdr,
        "hdr_format": hdr_format,
        "hdr_metadata_complete": hdr_metadata_complete,
        "hlg_metadata_complete": hlg_metadata_complete,
        "dolby_vision_detected": dolby_vision is not None,
        "dolby_vision_profile": dv_profile,
        "frame_rate_numeric": round(fps, 3) if fps is not None else None,
        "is_4k30_or_higher": is_4k30,
        "recommended_path": ("preserve_hdr" if hdr_metadata_complete else "inspect_color_metadata" if is_hdr else "sdr_to_hdr_optional" if transfer == "bt709" else "manual_color_confirmation"),
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
        "avg_frame_rate,r_frame_rate,color_range,color_space,color_transfer,color_primaries,side_data_list:"
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


VIDEO_PROCESSING_SLOT = __import__("threading").BoundedSemaphore(1)
VIDEO_PROCESS_TIMEOUT_SECONDS = 20 * 60


def _ffmpeg_filter(lut_path: Path, intensity: float) -> str:
    """Convert HLG/BT.2020 to SDR BT.709, apply a display-referred 3D LUT."""
    lut = str(lut_path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    amount = format(intensity, ".6f")
    return (
        "[0:v]zscale=t=linear:npl=1000,format=gbrpf32le,"
        "tonemap=mobius:desat=0,"
        "zscale=p=bt709:t=bt709:m=bt709:r=tv,"
        "format=gbrpf32le,split=2[base][forlut];"
        f"[forlut]lut3d=file='{lut}':interp=tetrahedral[graded];"
        f"[base][graded]blend=all_expr='A*(1-{amount})+B*{amount}',"
        "format=yuv420p10le[outv]"
    )


def transcode_hlg_video(source: Path, lut_path: Path, output: Path, intensity: float) -> None:
    """Render HLG source through an SDR BT.709 transform and a .cube LUT."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is not installed.")
    metadata = inspect_video(source)
    if not metadata["hlg_metadata_complete"]:
        raise ValueError(
            "This first video-processing workflow requires confirmed HLG, BT.2020, and at least 10-bit input."
        )
    # Parse once before invoking FFmpeg so malformed LUTs fail with a clear API error.
    core.parse_cube(lut_path)
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(source), "-filter_complex", _ffmpeg_filter(lut_path, intensity),
        "-map", "[outv]", "-map", "0:a?", "-c:v", "libx265",
        "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p10le",
        "-tag:v", "hvc1", "-color_primaries", "bt709",
        "-color_trc", "bt709", "-colorspace", "bt709",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True,
                       timeout=VIDEO_PROCESS_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Video processing exceeded the 20-minute time limit.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip()
        raise ValueError(detail[-1000:] or "FFmpeg could not process this video.") from exc
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("FFmpeg did not produce a valid output file.")


@router.post("/process")
async def process_uploaded_video(
    background_tasks: BackgroundTasks,
    video_file: UploadFile = File(...),
    cube: UploadFile = File(...),
    intensity: float = Form(1.0),
) -> FileResponse:
    """Apply a .cube LUT to confirmed HLG footage and export SDR BT.709 HEVC 10-bit MP4."""
    filename = Path((video_file.filename or "video").replace(chr(92), "/")).name
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_VIDEO_EXTENSIONS:
        raise HTTPException(400, "Supported video formats: MP4, MOV, M4V, and MKV.")
    if not (cube.filename or "").lower().endswith(".cube"):
        raise HTTPException(400, "LUT file must be .cube format.")
    if not 0.0 <= intensity <= 1.0:
        raise HTTPException(400, "LUT intensity must be between 0 and 1.")
    if not VIDEO_PROCESSING_SLOT.acquire(blocking=False):
        raise HTTPException(429, "The video processor is busy. Please retry when the current export finishes.")

    try:
        temp_dir = Path(tempfile.mkdtemp(prefix="photolut-video-process-"))
    except Exception:
        VIDEO_PROCESSING_SLOT.release()
        raise
    source = temp_dir / f"input{extension}"
    lut_path = temp_dir / "look.cube"
    output = temp_dir / "photolut_sdr_bt709_10bit.mp4"
    try:
        total = 0
        with source.open("wb") as stream:
            while chunk := await video_file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_VIDEO_BYTES:
                    raise HTTPException(413, "Video exceeds the 512 MiB processing limit.")
                stream.write(chunk)
        if total == 0:
            raise HTTPException(400, "The uploaded video is empty.")
        lut_size = 0
        with lut_path.open("wb") as stream:
            while chunk := await cube.read(1024 * 1024):
                lut_size += len(chunk)
                if lut_size > 10 * 1024 * 1024:
                    raise HTTPException(413, "LUT exceeds the 10 MiB limit.")
                stream.write(chunk)
        if lut_size == 0:
            raise HTTPException(400, "The uploaded LUT is empty.")
        try:
            await asyncio.to_thread(transcode_hlg_video, source, lut_path, output, intensity)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc

        background_tasks.add_task(shutil.rmtree, temp_dir, ignore_errors=True)
        return FileResponse(
            output, media_type="video/mp4",
            filename=f"{Path(filename).stem}_photolut_sdr_10bit.mp4",
            background=background_tasks,
        )
    except BaseException:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    finally:
        await video_file.close()
        await cube.close()
        VIDEO_PROCESSING_SLOT.release()
