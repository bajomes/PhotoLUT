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



def test_delete_job_output_removes_files_and_invalidates_archives(tmp_path, monkeypatch):
    job = app.jobs.create_job()
    job_id = job.id
    out_dir = tmp_path / job_id / "out"
    out_dir.mkdir(parents=True)
    names = ["before.jpg", "after.jpg", "sample.tiff", "sample.jpg"]
    for name in names + ["all.zip", "all-jpeg.zip", "all-tiff.zip"]:
        (out_dir / name).write_bytes(b"data")
    outputs = [{
        "id": "0", "filename": "sample.nef",
        "preview_before": f"/files/{job_id}/before.jpg",
        "preview_after": f"/files/{job_id}/after.jpg",
        "download_tiff": f"/files/{job_id}/sample.tiff",
        "download_jpeg": f"/files/{job_id}/sample.jpg",
    }]
    app.jobs.update_job(job_id, status=app.jobs.JobStatus.DONE, outputs=outputs)
    monkeypatch.setattr(app, "WORK_DIR", tmp_path)

    try:
        result = app.delete_job_output(job_id, "0")

        assert result == {"removed": "sample.nef", "outputs": []}
        assert app.jobs.get_job(job_id).outputs == []
        assert not any((out_dir / name).exists() for name in names)
        # Immutable ZIP snapshots are retained so an already-started
        # FileResponse can finish streaming after an output is removed.
    finally:
        with app.jobs._lock:
            app.jobs._jobs.pop(job_id, None)

def test_zip_snapshot_remains_valid_after_output_removal(tmp_path, monkeypatch):
    job = app.jobs.create_job()
    job_id = job.id
    out_dir = tmp_path / job_id / "out"
    out_dir.mkdir(parents=True)
    (out_dir / "sample.jpg").write_bytes(b"jpeg-data")
    (out_dir / "sample.tiff").write_bytes(b"tiff-data")
    outputs = [{
        "id": "0", "filename": "sample.nef",
        "preview_before": f"/files/{job_id}/before.jpg",
        "preview_after": f"/files/{job_id}/after.jpg",
        "download_tiff": f"/files/{job_id}/sample.tiff",
        "download_jpeg": f"/files/{job_id}/sample.jpg",
    }]
    app.jobs.update_job(job_id, status=app.jobs.JobStatus.DONE, outputs=outputs)
    monkeypatch.setattr(app, "WORK_DIR", tmp_path)

    try:
        first_response = app.download_zip(job_id, "all")
        first_archive = app.Path(first_response.path)
        with zipfile.ZipFile(first_archive) as archive:
            assert sorted(archive.namelist()) == ["sample.jpg", "sample.tiff"]
            assert archive.testzip() is None

        app.delete_job_output(job_id, "0")
        assert first_archive.is_file()
        with zipfile.ZipFile(first_archive) as archive:
            assert sorted(archive.namelist()) == ["sample.jpg", "sample.tiff"]
            assert archive.testzip() is None

        second_response = app.download_zip(job_id, "all")
        assert app.Path(second_response.path) != first_archive
        with zipfile.ZipFile(second_response.path) as archive:
            assert archive.namelist() == []
            assert archive.testzip() is None
    finally:
        with app.jobs._lock:
            app.jobs._jobs.pop(job_id, None)
            app.jobs._output_locks.pop(job_id, None)
