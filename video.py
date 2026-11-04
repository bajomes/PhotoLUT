"""Video metadata inspection and HLG HDR LUT processing."""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

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


def _parse_frame_rate(value: Any) -> float | None:
    """Parse an FFprobe frame-rate ratio, rejecting unknown or non-finite values."""
    try:
        numerator_text, denominator_text = str(value).split("/", 1)
        numerator = float(numerator_text)
        denominator = float(denominator_text)
    except (TypeError, ValueError):
        return None
    if (
        not np.isfinite(numerator)
        or not np.isfinite(denominator)
        or numerator <= 0
        or denominator <= 0
    ):
        return None
    rate = numerator / denominator
    return rate if np.isfinite(rate) else None


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
    hlg_metadata_complete = is_hlg and hdr_metadata_complete
    side_data = stream.get("side_data_list") or []
    dolby_vision = next((item for item in side_data
                         if "dovi" in str(item.get("side_data_type", "")).lower()
                         or "dolby vision" in str(item.get("side_data_type", "")).lower()), None)
    dv_profile = (dolby_vision or {}).get("dv_profile")
    hdr_side_data = []
    for item in side_data:
        side_type = str(item.get("side_data_type") or "").lower()
        if any(token in side_type for token in ("mastering display", "content light", "dovi", "dolby vision")):
            hdr_side_data.append({
                key: item[key] for key in (
                    "side_data_type", "red_x", "red_y", "green_x", "green_y",
                    "blue_x", "blue_y", "white_point_x", "white_point_y",
                    "min_luminance", "max_luminance", "max_content", "max_average",
                    "dv_profile", "dv_level", "rpu_present", "el_present",
                    "bl_present", "dv_bl_signal_compatibility_id",
                ) if key in item
            })
    hdr_side_data.sort(key=lambda item: str(item.get("side_data_type", "")))
    frame_rate = stream.get("avg_frame_rate")
    fps = _parse_frame_rate(frame_rate)
    if fps is None:
        # FFprobe can report avg_frame_rate as 0/0 or N/A for variable-rate
        # and some container streams. Use r_frame_rate when it is valid.
        fallback_rate = stream.get("r_frame_rate")
        fallback_fps = _parse_frame_rate(fallback_rate)
        if fallback_fps is not None:
            frame_rate, fps = fallback_rate, fallback_fps
        elif frame_rate is None:
            frame_rate = fallback_rate
    width, height = stream.get("width"), stream.get("height")
    is_4k30 = bool(width and height and max(width, height) >= 3840 and min(width, height) >= 2160 and fps is not None and fps >= 29.9)
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
        "frame_rate": frame_rate,
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
        "hdr_side_data": hdr_side_data,
        "frame_rate_numeric": round(fps, 3) if fps is not None else None,
        "is_4k30_or_higher": is_4k30,
        "recommended_path": ("apply_hlg_lut" if hlg_metadata_complete else "inspect_color_metadata" if is_hdr else "sdr_input" if transfer == "bt709" else "manual_color_confirmation"),
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
            inspection_task = asyncio.create_task(asyncio.to_thread(inspect_video, path))
            try:
                metadata = await asyncio.shield(inspection_task)
            except asyncio.CancelledError:
                try:
                    await inspection_task
                except Exception:
                    # Preserve request cancellation; the source file must stay
                    # available until FFprobe has stopped reading it.
                    pass
                raise
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


def _hlg_to_linear(signal: np.ndarray) -> np.ndarray:
    """Inverse HLG OETF for normalized HLG signal values."""
    value = np.clip(np.asarray(signal, dtype=np.float32), 0.0, 1.0)
    a = 0.17883277
    b = 1.0 - 4.0 * a
    c = 0.5 - a * np.log(4.0 * a)
    return np.where(value <= 0.5, value * value / 3.0,
                    (np.exp((value - c) / a) + b) / 12.0).astype(np.float32)


def _linear_to_hlg(linear: np.ndarray) -> np.ndarray:
    """HLG OETF for normalized scene-linear RGB values."""
    value = np.clip(np.asarray(linear, dtype=np.float32), 0.0, 1.0)
    a = 0.17883277
    b = 1.0 - 4.0 * a
    c = 0.5 - a * np.log(4.0 * a)
    return np.where(value <= (1.0 / 12.0), np.sqrt(3.0 * value),
                    a * np.log(np.maximum(12.0 * value - b, 1e-8)) + c).astype(np.float32)


def _lut_to_linear(signal: np.ndarray, lut_profile: str) -> np.ndarray:
    """Decode LUT-domain RGB values for a linear-light intensity blend."""
    value = np.clip(np.asarray(signal, dtype=np.float32), 0.0, 1.0)
    if lut_profile == "hlg":
        return _hlg_to_linear(value)
    if lut_profile == "rec709":
        # Rec.709 creative LUTs are display-referred. BT.1886's 2.4 EOTF
        # is the appropriate linear-light domain for blending their looks.
        return np.power(value, 2.4).astype(np.float32)
    raise ValueError("lut_profile must be 'hlg' or 'rec709'")


def _linear_to_lut(linear: np.ndarray, lut_profile: str) -> np.ndarray:
    """Encode linear-light RGB values back into the selected LUT domain."""
    value = np.clip(np.asarray(linear, dtype=np.float32), 0.0, 1.0)
    if lut_profile == "hlg":
        return _linear_to_hlg(value)
    if lut_profile == "rec709":
        return np.power(value, 1.0 / 2.4).astype(np.float32)
    raise ValueError("lut_profile must be 'hlg' or 'rec709'")


def _write_intensity_lut(
    lut: core.CubeLUT, intensity: float, output: Path, lut_profile: str = "hlg"
) -> None:
    """Bake LUT strength in its declared transfer domain for one GPU lookup."""
    if not 0.0 <= intensity <= 1.0:
        raise ValueError("intensity must be between 0.0 and 1.0")
    if lut_profile not in {"hlg", "rec709"}:
        raise ValueError("lut_profile must be 'hlg' or 'rec709'")
    red = np.linspace(lut.domain_min[0], lut.domain_max[0], lut.size, dtype=np.float32)
    green = np.linspace(lut.domain_min[1], lut.domain_max[1], lut.size, dtype=np.float32)
    blue = np.linspace(lut.domain_min[2], lut.domain_max[2], lut.size, dtype=np.float32)
    b_grid, g_grid, r_grid = np.meshgrid(blue, green, red, indexing="ij")
    identity = np.stack((r_grid, g_grid, b_grid), axis=-1)
    original_linear = _lut_to_linear(identity, lut_profile)
    graded_linear = _lut_to_linear(lut.table, lut_profile)
    mixed = original_linear * (1.0 - intensity) + graded_linear * intensity
    mixed_encoded = _linear_to_lut(mixed, lut_profile)

    with output.open("w", encoding="ascii", newline="\n") as stream:
        stream.write(f'TITLE "PhotoLUT GPU intensity-baked {lut_profile.upper()} LUT"\n')
        stream.write(f"LUT_3D_SIZE {lut.size}\n")
        stream.write("DOMAIN_MIN " + " ".join(f"{v:.8f}" for v in lut.domain_min) + "\n")
        stream.write("DOMAIN_MAX " + " ".join(f"{v:.8f}" for v in lut.domain_max) + "\n")
        # libplacebo normalizes .cube output samples through DOMAIN_MIN/MAX.
        # Serialize in the declared domain to preserve the blended RGB values.
        domain_span = lut.domain_max - lut.domain_min
        serialized_table = lut.domain_min + mixed_encoded * domain_span
        for rgb in serialized_table.reshape(-1, 3):
            stream.write(" ".join(f"{float(v):.8f}" for v in rgb) + "\n")


def _gpu_ffmpeg_filter(lut_path: Path, lut_profile: str = "hlg") -> str:
    """Build a Vulkan/libplacebo graph for HLG-domain or Rec.709 creative LUTs."""
    if lut_profile not in {"hlg", "rec709"}:
        raise ValueError("lut_profile must be 'hlg' or 'rec709'")
    lut = str(lut_path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    upload = "[0:v]hwdownload,format=p010le,hwupload,"
    if lut_profile == "rec709":
        # First create a properly tone-mapped SDR BT.709 image. The second
        # libplacebo pass applies the creative LUT to its intended native
        # BT.709 display-referred RGB values. The resulting export is SDR.
        return (
            upload
            + "libplacebo=tonemapping=bt.2390:format=p010le:"
            "colorspace=bt709:color_primaries=bt709:color_trc=bt709:"
            "range=tv:peak_detect=false,"
            + f"libplacebo=lut='{lut}':lut_type=native:format=p010le:"
            "colorspace=bt709:color_primaries=bt709:color_trc=bt709:"
            "range=tv:peak_detect=false,"
            "hwdownload,format=p010le[outv]"
        )
    return (
        upload
        + f"libplacebo=lut='{lut}':lut_type=native:format=p010le:"
        "colorspace=bt2020nc:color_primaries=bt2020:color_trc=arib-std-b67:"
        "range=tv:peak_detect=false,"
        "hwdownload,format=p010le[outv]"
    )


def _supports_gpu_lut(ffmpeg: str) -> bool:
    """Return true only when this FFmpeg exposes libplacebo's custom .cube option."""
    try:
        filters = subprocess.run(
            [ffmpeg, "-hide_banner", "-filters"], check=True,
            capture_output=True, text=True, timeout=15,
        )
        if not re.search(r"\blibplacebo\b", filters.stdout + filters.stderr):
            return False
        help_result = subprocess.run(
            [ffmpeg, "-hide_banner", "-h", "filter=libplacebo"],
            check=False, capture_output=True, text=True, timeout=15,
        )
        help_text = help_result.stdout + help_result.stderr
        return bool(re.search(r"^\s*lut\s+<", help_text, re.MULTILINE))
    except (OSError, subprocess.SubprocessError):
        return False


def transcode_hlg_video(
    source: Path, lut_path: Path, output: Path, intensity: float, lut_profile: str = "hlg"
) -> str:
    """Grade HLG source through NVIDIA GPU; output HLG or tone-mapped Rec.709 SDR."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is not installed.")
    metadata = inspect_video(source)
    if not metadata["hlg_metadata_complete"]:
        raise ValueError(
            "This first video-processing workflow requires confirmed HLG, BT.2020, and at least 10-bit input."
        )
    if metadata.get("dolby_vision_detected"):
        raise ValueError(
            "LUT export is disabled for Dolby Vision sources because re-encoding would discard Dolby Vision dynamic metadata."
        )
    if lut_profile not in {"hlg", "rec709"}:
        raise ValueError("LUT profile must be 'hlg' or 'rec709'.")
    parsed_lut = core.parse_cube(lut_path)
    if not 0.0 <= intensity <= 1.0:
        raise ValueError("intensity must be between 0.0 and 1.0")

    if not _supports_gpu_lut(ffmpeg):
        raise RuntimeError(
            "GPU export is unavailable: this FFmpeg build does not expose libplacebo custom .cube LUT support. "
            "CPU fallback is disabled to prevent unexpectedly high CPU load."
        )

    baked_lut = output.with_name(f"photolut-intensity-{lut_profile}.cube")

    if lut_profile == "hlg":
        output_color_args = [
            "-color_range", "tv", "-color_primaries", "bt2020",
            "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc",
        ]
    else:
        output_color_args = [
            "-color_range", "tv", "-color_primaries", "bt709",
            "-color_trc", "bt709", "-colorspace", "bt709",
        ]
    output_metadata_args = [
        "-tag:v", "hvc1", *output_color_args,
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output),
    ]

    selected_backend: str | None = None
    try:
        _write_intensity_lut(parsed_lut, intensity, baked_lut, lut_profile)
        # Select Vulkan by vendor name instead of an unstable physical-device index.
        # This prevents a hybrid laptop from silently grading on its integrated GPU
        # or a software Vulkan implementation.
        vulkan_device = "NVIDIA"
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "warning", "-y",
            "-init_hw_device", f"vulkan=vk:{vulkan_device}",
            "-filter_hw_device", "vk",
            "-hwaccel", "cuda", "-hwaccel_device", "0", "-hwaccel_output_format", "cuda",
            "-i", str(source), "-filter_complex", _gpu_ffmpeg_filter(baked_lut, lut_profile),
            "-map", "[outv]", "-map", "0:a?",
            "-c:v", "hevc_nvenc", "-gpu", "0", "-preset", "p5", "-tune", "hq",
            "-profile:v", "main10", "-pix_fmt", "p010le",
            "-rc", "vbr", "-cq", "19", "-b:v", "0",
        ] + output_metadata_args
        try:
            subprocess.run(
                command, check=True, capture_output=True, text=True,
                timeout=VIDEO_PROCESS_TIMEOUT_SECONDS,
            )
            selected_backend = (
                "GPU decode (NVDEC) + NVIDIA Vulkan/libplacebo HLG LUT + NVENC"
                if lut_profile == "hlg" else
                "GPU decode (NVDEC) + NVIDIA Vulkan/libplacebo HLG-to-SDR BT.709 tone map + Rec.709 LUT + NVENC"
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("GPU video processing exceeded the 20-minute time limit.") from exc
        except subprocess.CalledProcessError as exc:
            output.unlink(missing_ok=True)
            detail = (exc.stderr or exc.stdout or "").strip()
            raise RuntimeError(
                "GPU-only video export failed. CPU processing was not started. "
                "NVIDIA Vulkan/CUDA/NVENC diagnostics: "
                + (detail[-2400:] or "No FFmpeg diagnostic was returned.")
            ) from exc
        if not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError("FFmpeg did not produce a valid output file.")

        output_metadata = inspect_video(output)
        expected = {
            "codec": "hevc",
            "codec_profile": "Main 10",
            "pixel_format": "yuv420p10le",
            "bit_depth": 10,
            "color_transfer": "arib-std-b67" if lut_profile == "hlg" else "bt709",
            "color_primaries": "bt2020" if lut_profile == "hlg" else "bt709",
            "color_matrix": "bt2020nc" if lut_profile == "hlg" else "bt709",
        }
        mismatches = [
            f"{key}: expected {value!r}, got {output_metadata.get(key)!r}"
            for key, value in expected.items()
            if output_metadata.get(key) != value
        ]
        if mismatches:
            raise RuntimeError(
                "Export verification failed; output was rejected. " + "; ".join(mismatches)
            )
        return selected_backend
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    finally:
        baked_lut.unlink(missing_ok=True)



@router.post("/process")
async def process_uploaded_video(
    background_tasks: BackgroundTasks,
    video_file: UploadFile = File(...),
    cube: UploadFile = File(...),
    intensity: float = Form(1.0),
    lut_profile: str = Form("hlg"),
) -> FileResponse:
    """Apply a declared HLG or Rec.709 LUT to HLG source and verify the output."""
    filename = Path((video_file.filename or "video").replace(chr(92), "/")).name
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_VIDEO_EXTENSIONS:
        raise HTTPException(400, "Supported video formats: MP4, MOV, M4V, and MKV.")
    if not (cube.filename or "").lower().endswith(".cube"):
        raise HTTPException(400, "LUT file must be .cube format.")
    if not 0.0 <= intensity <= 1.0:
        raise HTTPException(400, "LUT intensity must be between 0 and 1.")
    if lut_profile not in {"hlg", "rec709"}:
        raise HTTPException(400, "LUT profile must be 'hlg' or 'rec709'.")
    if not VIDEO_PROCESSING_SLOT.acquire(blocking=False):
        raise HTTPException(429, "The video processor is busy. Please retry when the current export finishes.")

    try:
        temp_dir = Path(tempfile.mkdtemp(prefix="photolut-video-process-"))
    except Exception:
        VIDEO_PROCESSING_SLOT.release()
        raise
    source = temp_dir / f"input{extension}"
    lut_path = temp_dir / "look.cube"
    output = temp_dir / (
        "photolut_hdr_hlg_bt2020_10bit.mp4"
        if lut_profile == "hlg" else "photolut_sdr_bt709_10bit.mp4"
    )
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
        processing_task = asyncio.create_task(
            asyncio.to_thread(transcode_hlg_video, source, lut_path, output, intensity, lut_profile)
        )
        try:
            # Cancelling the request does not stop its FFmpeg worker thread.
            # Keep the GPU slot and temporary media alive until transcoding
            # actually exits, then let the outer cleanup run.
            processing_device = await asyncio.shield(processing_task)
        except asyncio.CancelledError:
            try:
                await processing_task
            except Exception:
                # Preserve request cancellation; do not mask it with a
                # secondary transcode error after the client has disconnected.
                pass
            raise
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc

        background_tasks.add_task(shutil.rmtree, temp_dir, ignore_errors=True)
        return FileResponse(
            output, media_type="video/mp4",
            filename=(
                f"{Path(filename).stem}_photolut_hdr_hlg_10bit.mp4"
                if lut_profile == "hlg" else
                f"{Path(filename).stem}_photolut_sdr_rec709_10bit.mp4"
            ),
            background=background_tasks,
            headers={
                "X-PhotoLUT-HDR-Verified": "true" if lut_profile == "hlg" else "false",
                "X-PhotoLUT-Output-Transfer": "arib-std-b67" if lut_profile == "hlg" else "bt709",
                "X-PhotoLUT-Output-Profile": lut_profile,
                "X-PhotoLUT-Processing-Device": processing_device,
                **({"X-PhotoLUT-HDR-Transfer": "arib-std-b67"} if lut_profile == "hlg" else {}),
            },
        )
    except BaseException:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    finally:
        VIDEO_PROCESSING_SLOT.release()
        await video_file.close()
        await cube.close()
