from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

import video


pytestmark = pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="FFmpeg and FFprobe are required for the video integration test",
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
        "-shortest", "-c:v", "libx265", "-preset", "ultrafast",
        "-x265-params", "log-level=error",
        "-pix_fmt", "yuv420p10le",
        "-color_primaries", "bt2020", "-color_trc", "arib-std-b67",
        "-colorspace", "bt2020nc", "-c:a", "aac", str(source),
    ])

    source_metadata = video.inspect_video(source)
    assert source_metadata["hlg_metadata_complete"] is True
    assert source_metadata["bit_depth"] == 10

    video.transcode_hlg_video(source, lut, output, 0.65)

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



@pytest.mark.parametrize(
    ("transfer", "expected_flag"),
    [("arib-std-b67", "is_hlg"), ("smpte2084", "is_pq")],
)
def test_synthetic_hdr_remux_preserves_transfer_and_10bit(
    tmp_path: Path, transfer: str, expected_flag: str
):
    """Exercise real FFmpeg HDR stream-copy remux and post-export verification."""
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg
    source = tmp_path / "synthetic_hdr_source.mp4"
    output = tmp_path / "preserved_hdr.mp4"
    _run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=64x64:rate=2:duration=1",
        "-c:v", "libx265", "-preset", "ultrafast",
        "-x265-params", "log-level=error",
        "-pix_fmt", "yuv420p10le",
        "-color_primaries", "bt2020", "-color_trc", transfer,
        "-colorspace", "bt2020nc", str(source),
    ])
    before = video.inspect_video(source)
    assert before["hdr_metadata_complete"] is True
    assert before[expected_flag] is True

    after = video.preserve_hdr_video(source, output)
    assert output.is_file() and output.stat().st_size > 0
    assert after["hdr_metadata_complete"] is True
    assert after["color_transfer"] == before["color_transfer"]
    assert after["color_primaries"] == before["color_primaries"]
    assert after["color_matrix"] == before["color_matrix"]
    assert after["bit_depth"] == before["bit_depth"]
    assert after["hdr_side_data"] == before["hdr_side_data"]
