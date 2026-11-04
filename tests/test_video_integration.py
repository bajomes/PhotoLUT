from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

import video


def _gpu_video_stack_skip_reason() -> str | None:
    """Skip only when FFmpeg lacks required compiled features.

    If the features are present, the integration test must execute the real
    CUDA -> Vulkan/libplacebo -> NVENC pipeline. A missing or unusable device
    is then a test failure, not a skip.
    """
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        return "GPU integration requires ffmpeg and ffprobe"

    try:
        encoders = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            check=True, capture_output=True, text=True, timeout=15,
        )
        filters = subprocess.run(
            [ffmpeg, "-hide_banner", "-filters"],
            check=True, capture_output=True, text=True, timeout=15,
        )
        help_result = subprocess.run(
            [ffmpeg, "-hide_banner", "-h", "filter=libplacebo"],
            check=False, capture_output=True, text=True, timeout=15,
        )
        hwaccels = subprocess.run(
            [ffmpeg, "-hide_banner", "-hwaccels"],
            check=True, capture_output=True, text=True, timeout=15,
        )
        devices = subprocess.run(
            [ffmpeg, "-hide_banner", "-init_hw_device", "list"],
            check=False, capture_output=True, text=True, timeout=15,
        )
        help_text = help_result.stdout + help_result.stderr
        device_text = devices.stdout + devices.stderr
        missing = []
        if "hevc_nvenc" not in encoders.stdout + encoders.stderr:
            missing.append("hevc_nvenc")
        if not re.search(r"\blibplacebo\b", filters.stdout + filters.stderr):
            missing.append("libplacebo")
        if re.search(r"^\s*lut\s+<", help_text, re.MULTILINE) is None:
            missing.append("libplacebo custom .cube LUT option")
        if not re.search(r"^cuda$", hwaccels.stdout + hwaccels.stderr, re.MULTILINE):
            missing.append("CUDA hwaccel")
        if not re.search(r"(?:^|[,\s])vulkan(?:$|[,\s])", device_text, re.IGNORECASE):
            missing.append("Vulkan hardware device support")
        if missing:
            return "FFmpeg build lacks required GPU features: " + ", ".join(missing)
        return None
    except (OSError, subprocess.SubprocessError) as exc:
        # A broken or unresponsive FFmpeg probe is not evidence that a build
        # feature is absent. Fail collection rather than silently skipping the
        # hardware integration test and masking a damaged runtime environment.
        raise RuntimeError(f"Could not inspect FFmpeg GPU capabilities: {exc}") from exc

GPU_VIDEO_SKIP_REASON = _gpu_video_stack_skip_reason()
pytestmark = pytest.mark.skipif(
    GPU_VIDEO_SKIP_REASON is not None,
    reason=GPU_VIDEO_SKIP_REASON or "Required FFmpeg GPU features are unavailable",
)


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True, text=True, timeout=60)


def test_synthetic_hlg_video_exports_real_10bit_hlg_bt2020_mp4(tmp_path: Path):
    """Exercise FFmpeg, LUT parsing, HLG gating, encoding, and output metadata."""
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    assert ffmpeg and ffprobe

    source = tmp_path / "synthetic_hlg.mp4"
    lut = tmp_path / "identity.cube"
    output = tmp_path / "graded.mp4"

    # A small 2x2x2 identity LUT, written as an actual text .cube file.
    lut.write_text(
        "TITLE \"PhotoLUT integration identity\"\n"
        "LUT_3D_SIZE 2\n"
        "0 0 0\n"
        "1 0 0\n"
        "0 1 0\n"
        "1 1 0\n"
        "0 0 1\n"
        "1 0 1\n"
        "0 1 1\n"
        "1 1 1\n",
        encoding="utf-8",
    )

    _run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=64x64:rate=2:duration=1",
        "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=48000:duration=1",
        "-shortest",
        "-vf",
        "zscale=matrixin=bt709:transferin=bt709:primariesin=bt709:rangein=limited:"
        "matrix=bt2020nc:transfer=arib-std-b67:primaries=bt2020:range=limited,"
        "format=yuv420p10le",
        "-c:v", "libx265", "-preset", "ultrafast", "-crf", "12",
        "-x265-params", "log-level=error",
        "-color_primaries", "bt2020", "-color_trc", "arib-std-b67",
        "-colorspace", "bt2020nc", "-c:a", "aac", str(source),
    ])

    source_metadata = video.inspect_video(source)
    assert source_metadata["hlg_metadata_complete"] is True
    assert source_metadata["bit_depth"] == 10

    backend = video.transcode_hlg_video(source, lut, output, 0.65)
    assert backend == "GPU decode (NVDEC) + NVIDIA Vulkan/libplacebo HLG LUT + NVENC"

    result = video.inspect_video(output)
    assert output.is_file() and output.stat().st_size > 0
    assert result["codec"] == "hevc"
    assert result["bit_depth"] == 10
    assert result["pixel_format"] == "yuv420p10le"
    assert result["color_primaries"] == "bt2020"
    assert result["color_transfer"] == "arib-std-b67"
    assert result["color_matrix"] == "bt2020nc"

    probe = subprocess.run(
        [
            ffprobe, "-v", "error", "-show_entries", "stream=codec_type,codec_name",
            "-of", "csv=p=0", str(output),
        ],
        check=True, capture_output=True, text=True, timeout=30,
    )
    streams = {
        tuple(field.strip() for field in line.split(","))
        for line in probe.stdout.splitlines()
        if line.strip()
    }
    assert ("video", "hevc") in streams or ("hevc", "video") in streams
    assert ("audio", "aac") in streams or ("aac", "audio") in streams

    # The identity LUT must leave a correctly converted HLG signal visually
    # close to the source after the decode/encode round trip.
    comparison = subprocess.run(
        [
            ffmpeg, "-hide_banner", "-i", str(source), "-i", str(output),
            "-filter_complex", "[0:v:0][1:v:0]psnr=shortest=1",
            "-an", "-f", "null", "-",
        ],
        check=True, capture_output=True, text=True, timeout=30,
    )
    match = re.search(r"average:([0-9.]+)", comparison.stderr)
    assert match, comparison.stderr
    assert float(match.group(1)) > 30.0, comparison.stderr

    # The Rec.709 profile must run the full two-pass Vulkan path: HLG tone
    # mapping first, then the creative LUT in native SDR BT.709 RGB.
    sdr_output = tmp_path / "graded_rec709.mp4"
    sdr_backend = video.transcode_hlg_video(source, lut, sdr_output, 0.65, "rec709")
    assert sdr_backend == (
        "GPU decode (NVDEC) + NVIDIA Vulkan/libplacebo HLG-to-SDR BT.709 "
        "tone map + Rec.709 LUT + NVENC"
    )

    sdr_result = video.inspect_video(sdr_output)
    assert sdr_output.is_file() and sdr_output.stat().st_size > 0
    assert sdr_result["codec"] == "hevc"
    assert sdr_result["codec_profile"] == "Main 10"
    assert sdr_result["bit_depth"] == 10
    assert sdr_result["pixel_format"] == "yuv420p10le"
    assert sdr_result["color_primaries"] == "bt709"
    assert sdr_result["color_transfer"] == "bt709"
    assert sdr_result["color_matrix"] == "bt709"
    assert sdr_result["is_hdr"] is False
