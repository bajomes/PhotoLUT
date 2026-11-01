from __future__ import annotations

import zipfile
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import numpy as np
import pytest
import tifffile
from PIL import Image

import app


def test_output_files_embed_srgb_profiles_and_metadata_status(tmp_path, monkeypatch):
    monkeypatch.setattr(app.core, "copy_metadata", lambda *_args: True)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    raw_path = tmp_path / "sample.nef"
    before = np.full((8, 10, 3), 0.25, dtype=np.float32)
    graded = np.full((8, 10, 3), 0.6, dtype=np.float32)

    paths, metadata_ok = app._save_outputs(
        graded, before, out_dir, "sample", 0, raw_path
    )

    assert metadata_ok is True
    with Image.open(paths["jpeg"]) as image:
        assert image.mode == "RGB"
        assert image.info.get("icc_profile")

    with tifffile.TiffFile(paths["tiff"]) as tif:
        page = tif.pages[0]
        assert page.dtype == np.uint16
        assert 34675 in page.tags
        assert len(page.tags[34675].value) > 0


def test_output_stem_does_not_keep_path_or_markup():
    stem = app._safe_output_stem("../../summer beach<script>.CR3")

    assert "/" not in stem
    assert "\\" not in stem
    assert "<" not in stem and ">" not in stem
    assert stem


@pytest.mark.parametrize(
    ("archive_format", "expected_members"),
    [
        ("jpeg", ["sample_lut.jpg"]),
        ("tiff", ["sample_lut.tiff"]),
        ("all", ["sample_lut.jpg", "sample_lut.tiff"]),
    ],
)
def test_download_zip_selects_requested_format(
    tmp_path, monkeypatch, archive_format, expected_members
):
    job_id = "job123"
    out_dir = tmp_path / job_id / "out"
    out_dir.mkdir(parents=True)
    (out_dir / "sample_lut.jpg").write_bytes(b"fake jpeg")
    (out_dir / "sample_lut.tiff").write_bytes(b"fake tiff")

    job = SimpleNamespace(
        id=job_id,
        status=app.jobs.JobStatus.DONE,
        outputs=[{
            "download_jpeg": f"/files/{job_id}/sample_lut.jpg",
            "download_tiff": f"/files/{job_id}/sample_lut.tiff",
        }],
    )
    monkeypatch.setattr(app, "WORK_DIR", tmp_path)
    monkeypatch.setattr(app.jobs, "get_job", lambda _job_id: job)

    response = app.download_zip(job_id, archive_format)
    assert response.media_type == "application/zip"
    with zipfile.ZipFile(response.path) as archive:
        assert sorted(archive.namelist()) == sorted(expected_members)


def test_download_zip_rejects_unknown_format():
    with pytest.raises(app.HTTPException) as exc_info:
        app.download_zip("job123", "png")

    assert exc_info.value.status_code == 400



def test_download_zip_is_safe_for_concurrent_requests(tmp_path, monkeypatch):
    job_id = "job123"
    out_dir = tmp_path / job_id / "out"
    out_dir.mkdir(parents=True)
    (out_dir / "sample_lut.jpg").write_bytes(b"fake jpeg")
    (out_dir / "sample_lut.tiff").write_bytes(b"fake tiff")
    job = SimpleNamespace(
        id=job_id,
        status=app.jobs.JobStatus.DONE,
        outputs=[{
            "download_jpeg": f"/files/{job_id}/sample_lut.jpg",
            "download_tiff": f"/files/{job_id}/sample_lut.tiff",
        }],
    )
    monkeypatch.setattr(app, "WORK_DIR", tmp_path)
    monkeypatch.setattr(app.jobs, "get_job", lambda _job_id: job)

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: app.download_zip(job_id, "all"), range(16)))

    for response in responses:
        with zipfile.ZipFile(response.path) as archive:
            assert sorted(archive.namelist()) == ["sample_lut.jpg", "sample_lut.tiff"]
            assert archive.testzip() is None
    assert not list(out_dir.glob(".all.zip.*.tmp"))


def test_process_uploads_before_acquiring_processing_slot(client, monkeypatch):
    events = []

    async def save_upload(upload, dest, max_bytes, remaining_total_bytes):
        events.append("upload")
        dest.write_bytes(await upload.read())
        return dest.stat().st_size

    class Slots:
        def acquire(self, blocking=False):
            events.append("acquire")
            return True

        def release(self):
            events.append("release")

    monkeypatch.setattr(app, "_save_upload", save_upload)
    monkeypatch.setattr(app, "PROCESSING_SLOTS", Slots())
    monkeypatch.setattr(app, "_process_job_sync", lambda *_args: None)

    response = post_process(client)
    assert response.status_code == 200, response.text
    assert events.count("upload") == 2
    assert events.index("acquire") > max(i for i, event in enumerate(events) if event == "upload")
