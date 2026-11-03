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
    assert result["recommended_path"] == "sdr_input"


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


def test_preserve_hdr_rejects_unconfirmed_source(tmp_path: Path):
    source, output = tmp_path / "in.mp4", tmp_path / "out.mp4"
    source.write_bytes(b"video")
    with patch("video.shutil.which", return_value="/usr/bin/ffmpeg"), patch(
        "video.inspect_video", return_value={"hdr_metadata_complete": False}
    ), patch("video.subprocess.run") as run:
        with pytest.raises(ValueError, match="requires confirmed"):
            video.preserve_hdr_video(source, output)
    run.assert_not_called()


def test_preserve_hdr_stream_copies_and_verifies_metadata(tmp_path: Path):
    source, output = tmp_path / "in.mp4", tmp_path / "out.mp4"
    source.write_bytes(b"video")
    metadata = {"hdr_metadata_complete": True, "codec": "hevc", "color_transfer": "arib-std-b67",
                "color_primaries": "bt2020", "color_matrix": "bt2020nc", "bit_depth": 10}
    def fake_run(command, **kwargs):
        Path(command[-1]).write_bytes(b"mp4")
        assert "copy" in command
        assert "-tag:v" in command and "hvc1" in command
        return subprocess.CompletedProcess(command, 0, "", "")
    with patch("video.shutil.which", return_value="/usr/bin/ffmpeg"), patch(
        "video.inspect_video", side_effect=[metadata, metadata]
    ), patch("video.subprocess.run", side_effect=fake_run):
        result = video.preserve_hdr_video(source, output)
    assert result["hdr_metadata_complete"] is True
    assert output.read_bytes() == b"mp4"


def test_transcode_rejects_dolby_vision_before_ffmpeg(tmp_path: Path):
    source, lut, output = (tmp_path / name for name in ("in.mp4", "look.cube", "out.mp4"))
    source.write_bytes(b"video")
    lut.write_text("LUT_3D_SIZE 2\n" + "0 0 0\n" * 8)
    metadata = {"hlg_metadata_complete": True, "dolby_vision_detected": True}
    with patch("video.shutil.which", return_value="/usr/bin/ffmpeg"), patch(
        "video.inspect_video", return_value=metadata
    ), patch("video.subprocess.run") as run:
        with pytest.raises(ValueError, match="Dolby Vision sources"):
            video.transcode_hlg_video(source, lut, output, 1.0)
    run.assert_not_called()
    assert not output.exists()


def test_transcode_rejects_unconfirmed_hlg_before_ffmpeg(tmp_path: Path):
    source, lut, output = (tmp_path / name for name in ("in.mp4", "look.cube", "out.mp4"))
    source.write_bytes(b"video")
    lut.write_text("LUT_3D_SIZE 2\n" + "0 0 0\n" * 8)
    metadata = {"hlg_metadata_complete": False}
    with patch("video.shutil.which", return_value="/usr/bin/ffmpeg"), patch(
        "video.inspect_video", return_value=metadata
    ), patch("video.subprocess.run") as run:
        with pytest.raises(ValueError, match="requires confirmed HLG"):
            video.transcode_hlg_video(source, lut, output, 1.0)
    run.assert_not_called()


def test_transcode_invokes_ffmpeg_as_ten_bit_hlg_bt2020(tmp_path: Path):
    source, lut, output = (tmp_path / name for name in ("in.mp4", "look.cube", "out.mp4"))
    source.write_bytes(b"video")
    lut.write_text("LUT_3D_SIZE 2\n" + "0 0 0\n" * 8)
    def fake_run(command, **kwargs):
        Path(command[-1]).write_bytes(b"mp4")
        return subprocess.CompletedProcess(command, 0, "", "")
    source_metadata = {"hlg_metadata_complete": True}
    output_metadata = {
        "codec": "hevc", "codec_profile": "Main 10",
        "pixel_format": "yuv420p10le", "bit_depth": 10,
        "color_transfer": "arib-std-b67", "color_primaries": "bt2020",
        "color_matrix": "bt2020nc",
    }
    with patch("video.shutil.which", return_value="/usr/bin/ffmpeg"), patch(
        "video.inspect_video", side_effect=[source_metadata, output_metadata]
    ), patch("video.core.parse_cube"), patch("video.subprocess.run", side_effect=fake_run) as run:
        video.transcode_hlg_video(source, lut, output, 0.5)
    command = run.call_args.args[0]
    assert "-pix_fmt" in command and command[command.index("-pix_fmt") + 1] == "yuv420p10le"
    assert command[command.index("-color_trc") + 1] == "arib-std-b67"
    assert command[command.index("-color_primaries") + 1] == "bt2020"
    assert command[command.index("-colorspace") + 1] == "bt2020nc"
    graph = command[command.index("-filter_complex") + 1]
    assert "tonemap=" not in graph
    assert "transfer=arib-std-b67" in graph
    assert "lut3d=" in graph
    assert output.read_bytes() == b"mp4"



def test_normalize_preserves_hdr_mastering_and_dolby_vision_side_data():
    payload = json.loads(json.dumps(HLG_PAYLOAD))
    payload["streams"][0]["side_data_list"] = [
        {"side_data_type": "Mastering display metadata", "red_x": "0.68",
         "max_luminance": "1000 cd/m2"},
        {"side_data_type": "Content light level metadata", "max_content": 1000,
         "max_average": 400},
        {"side_data_type": "DOVI configuration record", "dv_profile": 8,
         "dv_level": 6, "rpu_present": 1},
        {"side_data_type": "Display Matrix", "rotation": 90},
    ]
    result = video.normalize_probe_data(payload)
    assert len(result["hdr_side_data"]) == 3
    assert result["dolby_vision_detected"] is True
    assert result["dolby_vision_profile"] == 8


def test_preserve_hdr_rejects_changed_mastering_metadata(tmp_path: Path):
    source, output = tmp_path / "in.mp4", tmp_path / "out.mp4"
    source.write_bytes(b"video")
    source_metadata = {
        "hdr_metadata_complete": True, "codec": "hevc",
        "color_transfer": "smpte2084", "color_primaries": "bt2020",
        "color_matrix": "bt2020nc", "bit_depth": 10,
        "hdr_side_data": [{"side_data_type": "Content light level metadata",
                           "max_content": 1000, "max_average": 400}],
    }
    output_metadata = {**source_metadata, "hdr_side_data": []}

    def fake_run(command, **kwargs):
        Path(command[-1]).write_bytes(b"mp4")
        return subprocess.CompletedProcess(command, 0, "", "")

    with patch("video.shutil.which", return_value="/usr/bin/ffmpeg"), patch(
        "video.inspect_video", side_effect=[source_metadata, output_metadata]
    ), patch("video.subprocess.run", side_effect=fake_run):
        with pytest.raises(RuntimeError, match="hdr_side_data"):
            video.preserve_hdr_video(source, output)

    assert not output.exists()



def test_transcode_rejects_unexpected_h264_output(tmp_path: Path):
    source, lut, output = (tmp_path / name for name in ("in.mp4", "look.cube", "out.mp4"))
    source.write_bytes(b"video")
    lut.write_text("LUT_3D_SIZE 2\n" + "0 0 0\n" * 8)

    source_metadata = {"hlg_metadata_complete": True}
    bad_output_metadata = {
        "codec": "h264", "codec_profile": "High 10",
        "pixel_format": "yuv420p10le", "bit_depth": 10,
        "color_transfer": "bt709", "color_primaries": "bt709",
        "color_matrix": "bt709",
    }

    def fake_run(command, **kwargs):
        Path(command[-1]).write_bytes(b"mp4")
        return subprocess.CompletedProcess(command, 0, "", "")

    with patch("video.shutil.which", return_value="/usr/bin/ffmpeg"), patch(
        "video.inspect_video", side_effect=[source_metadata, bad_output_metadata]
    ), patch("video.core.parse_cube"), patch("video.subprocess.run", side_effect=fake_run):
        with pytest.raises(RuntimeError, match="codec: expected 'hevc', got 'h264'"):
            video.transcode_hlg_video(source, lut, output, 1.0)

    assert not output.exists()


def test_preserve_hdr_removes_partial_output_when_ffmpeg_fails(tmp_path: Path):
    source, output = tmp_path / "in.mp4", tmp_path / "out.mp4"
    source.write_bytes(b"video")
    metadata = {"hdr_metadata_complete": True, "codec": "hevc"}
    def fake_run(command, **kwargs):
        Path(command[-1]).write_bytes(b"partial")
        raise subprocess.CalledProcessError(1, command, stderr="mux failed")
    with patch("video.shutil.which", return_value="/usr/bin/ffmpeg"), patch(
        "video.inspect_video", return_value=metadata
    ), patch("video.subprocess.run", side_effect=fake_run):
        with pytest.raises(ValueError, match="mux failed"):
            video.preserve_hdr_video(source, output)
    assert not output.exists()


def test_preserve_hdr_removes_output_when_reprobe_fails(tmp_path: Path):
    source, output = tmp_path / "in.mp4", tmp_path / "out.mp4"
    source.write_bytes(b"video")
    metadata = {"hdr_metadata_complete": True, "codec": "hevc", "color_transfer": "arib-std-b67",
                "color_primaries": "bt2020", "color_matrix": "bt2020nc", "bit_depth": 10,
                "hdr_side_data": []}
    def fake_run(command, **kwargs):
        Path(command[-1]).write_bytes(b"mp4")
        return subprocess.CompletedProcess(command, 0, "", "")
    with patch("video.shutil.which", return_value="/usr/bin/ffmpeg"), patch(
        "video.inspect_video", side_effect=[metadata, RuntimeError("ffprobe failed")]
    ), patch("video.subprocess.run", side_effect=fake_run):
        with pytest.raises(RuntimeError, match="ffprobe failed"):
            video.preserve_hdr_video(source, output)
    assert not output.exists()


def test_transcode_removes_partial_output_when_ffmpeg_fails(tmp_path: Path):
    source, lut, output = (tmp_path / name for name in ("in.mp4", "look.cube", "out.mp4"))
    source.write_bytes(b"video")
    lut.write_text("LUT_3D_SIZE 2\n" + "0 0 0\n" * 8)
    with patch("video.shutil.which", return_value="/usr/bin/ffmpeg"), patch(
        "video.inspect_video", return_value={"hlg_metadata_complete": True}
    ), patch("video.core.parse_cube"), patch("video.subprocess.run") as run:
        def fake_run(command, **kwargs):
            Path(command[-1]).write_bytes(b"partial")
            raise subprocess.CalledProcessError(1, command, stderr="encode failed")
        run.side_effect = fake_run
        with pytest.raises(ValueError, match="encode failed"):
            video.transcode_hlg_video(source, lut, output, 1.0)
    assert not output.exists()


def test_transcode_removes_output_when_reprobe_fails(tmp_path: Path):
    source, lut, output = (tmp_path / name for name in ("in.mp4", "look.cube", "out.mp4"))
    source.write_bytes(b"video")
    lut.write_text("LUT_3D_SIZE 2\n" + "0 0 0\n" * 8)
    def fake_run(command, **kwargs):
        Path(command[-1]).write_bytes(b"mp4")
        return subprocess.CompletedProcess(command, 0, "", "")
    with patch("video.shutil.which", return_value="/usr/bin/ffmpeg"), patch(
        "video.inspect_video", side_effect=[{"hlg_metadata_complete": True}, RuntimeError("ffprobe failed")]
    ), patch("video.core.parse_cube"), patch("video.subprocess.run", side_effect=fake_run):
        with pytest.raises(RuntimeError, match="ffprobe failed"):
            video.transcode_hlg_video(source, lut, output, 1.0)
    assert not output.exists()


def test_builtin_natural_hlg_lut_is_valid_and_bounded():
    lut = Path(__file__).resolve().parents[1] / "static" / "luts" / "photolut-natural-hlg-bt2020.cube"
    parsed = video.core.parse_cube(lut)
    assert parsed.size == 33
    assert parsed.table.min() >= 0.0
    assert parsed.table.max() <= 1.0


def test_hlg_filter_does_not_tone_map_to_sdr(tmp_path: Path):
    graph = video._ffmpeg_filter(tmp_path / "natural.cube", 1.0)
    assert "tonemap=" not in graph
    assert "bt709" not in graph
    assert "transfer=arib-std-b67" in graph
    assert "primaries=bt2020" in graph
    assert "format=yuv420p10le[outv]" in graph
