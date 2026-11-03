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


def test_normalize_identifies_pq_hdr10_and_4k30():
    payload = json.loads(json.dumps(HLG_PAYLOAD))
    stream = payload["streams"][0]
    stream["color_transfer"] = "smpte2084"
    result = video.normalize_probe_data(payload)
    assert result["is_pq"] is True
    assert result["is_hdr"] is True
    assert result["hdr_format"] == "HDR10 / PQ"
    assert result["hdr_metadata_complete"] is True
    assert result["is_4k30_or_higher"] is True
    assert result["recommended_path"] == "preserve_hdr"


def test_normalize_does_not_call_sdr_hdr_or_force_upscale():
    payload = json.loads(json.dumps(HLG_PAYLOAD))
    stream = payload["streams"][0]
    stream.update(width=1920, height=1080, avg_frame_rate="30/1", color_transfer="bt709",
                  color_primaries="bt709", color_space="bt709", pix_fmt="yuv420p")
    result = video.normalize_probe_data(payload)
    assert result["is_hdr"] is False
    assert result["hdr_format"] == "SDR / BT.709"
    assert result["is_4k30_or_higher"] is False
    assert result["recommended_path"] == "sdr_to_hdr_optional"


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


def test_video_filter_keeps_ten_bit_and_applies_intensity(tmp_path: Path):
    lut = tmp_path / "look.cube"
    graph = video._ffmpeg_filter(lut, 0.35)
    assert "lut3d=" in graph
    assert "A*(1-0.350000)+B*0.350000" in graph
    assert "format=yuv420p10le[outv]" in graph


def test_transcode_rejects_unconfirmed_hlg_before_ffmpeg(tmp_path: Path):
    source, lut, output = (tmp_path / name for name in ("in.mp4", "look.cube", "out.mp4"))
    source.write_bytes(b"video")
    lut.write_text("LUT_3D_SIZE 2\\n" + "0 0 0\\n" * 8)
    metadata = {"hlg_metadata_complete": False}
    with patch("video.shutil.which", return_value="/usr/bin/ffmpeg"), patch(
        "video.inspect_video", return_value=metadata
    ), patch("video.subprocess.run") as run:
        with pytest.raises(ValueError, match="requires confirmed HLG"):
            video.transcode_hlg_video(source, lut, output, 1.0)
    run.assert_not_called()


def test_transcode_invokes_ffmpeg_as_ten_bit_bt709(tmp_path: Path):
    source, lut, output = (tmp_path / name for name in ("in.mp4", "look.cube", "out.mp4"))
    source.write_bytes(b"video")
    lut.write_text("LUT_3D_SIZE 2\\n" + "0 0 0\\n" * 8)
    def fake_run(command, **kwargs):
        Path(command[-1]).write_bytes(b"mp4")
        return subprocess.CompletedProcess(command, 0, "", "")
    with patch("video.shutil.which", return_value="/usr/bin/ffmpeg"), patch(
        "video.inspect_video", return_value={"hlg_metadata_complete": True}
    ), patch("video.core.parse_cube"), patch("video.subprocess.run", side_effect=fake_run) as run:
        video.transcode_hlg_video(source, lut, output, 0.5)
    command = run.call_args.args[0]
    assert "-pix_fmt" in command and command[command.index("-pix_fmt") + 1] == "yuv420p10le"
    assert command[command.index("-color_trc") + 1] == "bt709"
    assert output.read_bytes() == b"mp4"
