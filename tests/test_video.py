from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

import video


HLG_PAYLOAD = {
    "streams": [{
        "codec_type": "video",
        "codec_name": "hevc",
        "profile": "Main 10",
        "width": 3840,
        "height": 2160,
        "pix_fmt": "yuv420p10le",
        "avg_frame_rate": "30/1",
        "color_range": "tv",
        "color_space": "bt2020nc",
        "color_transfer": "arib-std-b67",
        "color_primaries": "bt2020",
    }],
    "format": {"duration": "12.5", "format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
}


def test_normalize_identifies_complete_hlg10_metadata():
    result = video.normalize_probe_data(HLG_PAYLOAD)
    assert result["is_hlg"] is True
    assert result["hlg_metadata_complete"] is True
    assert result["bit_depth"] == 10
    assert result["color_primaries"] == "bt2020"
    assert result["duration_seconds"] == 12.5
    assert result["warnings"] == []


def test_hlg_transfer_without_complete_metadata_is_flagged():
    payload = json.loads(json.dumps(HLG_PAYLOAD))
    payload["streams"][0]["color_primaries"] = "unknown"
    result = video.normalize_probe_data(payload)
    assert result["is_hlg"] is True
    assert result["hlg_metadata_complete"] is False
    assert any("could not be confirmed" in warning for warning in result["warnings"])


def test_non_hlg_video_is_not_mislabeled():
    payload = json.loads(json.dumps(HLG_PAYLOAD))
    payload["streams"][0]["color_transfer"] = "bt709"
    result = video.normalize_probe_data(payload)
    assert result["is_hlg"] is False
    assert result["hlg_metadata_complete"] is False


def test_missing_video_stream_is_rejected():
    with pytest.raises(ValueError, match="No video stream"):
        video.normalize_probe_data({"streams": [], "format": {}})


def test_inspect_video_invokes_ffprobe_without_shell(tmp_path: Path):
    source = tmp_path / "sample.mp4"
    source.write_bytes(b"fake")
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps(HLG_PAYLOAD), stderr="")
    with patch("video.shutil.which", return_value="/usr/bin/ffprobe"), patch(
        "video.subprocess.run", return_value=completed
    ) as run:
        result = video.inspect_video(source)
    assert result["hlg_metadata_complete"] is True
    args, kwargs = run.call_args
    assert args[0][0] == "/usr/bin/ffprobe"
    assert kwargs["timeout"] == video.FFPROBE_TIMEOUT_SECONDS
    assert kwargs["check"] is True


def test_inspect_video_reports_timeout(tmp_path: Path):
    source = tmp_path / "sample.mp4"
    source.write_bytes(b"fake")
    with patch("video.shutil.which", return_value="/usr/bin/ffprobe"), patch(
        "video.subprocess.run", side_effect=subprocess.TimeoutExpired("ffprobe", 20)
    ):
        with pytest.raises(RuntimeError, match="timed out"):
            video.inspect_video(source)
