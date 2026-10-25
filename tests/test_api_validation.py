from __future__ import annotations

import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

import app
import jobs


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "WORK_DIR", tmp_path)
    with jobs._lock:
        known_ids = set(jobs._jobs)
    test_client = TestClient(app.app)
    yield test_client
    with jobs._lock:
        for job_id in set(jobs._jobs) - known_ids:
            jobs._jobs.pop(job_id, None)


def make_cube() -> bytes:
    rows = []
    for blue in (0.0, 1.0):
        for green in (0.0, 1.0):
            for red in (0.0, 1.0):
                rows.append(f"{red} {green} {blue}")
    return ("LUT_3D_SIZE 2\\n" + "\\n".join(rows) + "\\n").encode("utf-8")


def post_process(
    client,
    *,
    raw_names=("sample.nef",),
    cube_name="identity.cube",
    cube_content=None,
    data=None,
):
    files = [
        ("raw_files", (name, b"raw-fixture", "application/octet-stream"))
        for name in raw_names
    ]
    files.append((
        "cube",
        (cube_name, make_cube() if cube_content is None else cube_content, "text/plain"),
    ))
    form = {"colorspace": "srgb", "intensity": "1.0"}
    if data:
        form.update(data)
    return client.post("/api/process", files=files, data=form)


def test_rejects_non_cube_lut_extension(client):
    response = post_process(client, cube_name="look.txt")
    assert response.status_code == 400
    assert response.json() == {"detail": "LUT file must be .cube format"}


def test_rejects_unsupported_raw_extension(client):
    response = post_process(client, raw_names=("sample.png",))
    assert response.status_code == 400
    assert response.json() == {"detail": "Unsupported RAW format: .png"}


def test_rejects_camera_log_colorspace(client):
    response = post_process(client, data={"colorspace": "log"})
    assert response.status_code == 400
    assert "Only sRGB input is supported" in response.json()["detail"]


def test_rejects_intensity_outside_range(client):
    response = post_process(client, data={"intensity": "1.01"})
    assert response.status_code == 400
    assert response.json() == {"detail": "Intensity must be between 0.0 and 1.0"}


def test_rejects_batch_over_file_count_limit(client, monkeypatch):
    monkeypatch.setattr(app, "MAX_RAW_FILES", 1)
    response = post_process(client, raw_names=("one.nef", "two.nef"))
    assert response.status_code == 413
    assert "at most 1 RAW files" in response.json()["detail"]


def test_rejects_lut_upload_over_size_limit(client, monkeypatch):
    monkeypatch.setattr(app, "MAX_CUBE_BYTES", 2)
    response = post_process(client, cube_content=b"abc")
    assert response.status_code == 413
    assert response.json()["detail"] == "identity.cube exceeds its size limit"


def test_rejects_raw_upload_over_size_limit(client, monkeypatch):
    monkeypatch.setattr(app, "MAX_RAW_BYTES", 2)
    files = [
        ("raw_files", ("sample.nef", b"abc", "application/octet-stream")),
        ("cube", ("identity.cube", make_cube(), "text/plain")),
    ]
    response = client.post("/api/process", files=files, data={"colorspace": "srgb", "intensity": "1"})
    assert response.status_code == 413
    assert response.json()["detail"] == "sample.nef exceeds its size limit"


def test_rejects_batch_over_total_upload_limit(client, monkeypatch):
    monkeypatch.setattr(app, "MAX_TOTAL_UPLOAD_BYTES", 3)
    response = post_process(client, cube_content=b"123")
    assert response.status_code == 413
    assert "total upload limit" in response.json()["detail"]


def test_returns_busy_when_all_processing_slots_are_taken(client, monkeypatch):
    class BusySlots:
        def acquire(self, blocking=False):
            return False

        def release(self):
            raise AssertionError("release should not be called when acquire fails")

    monkeypatch.setattr(app, "PROCESSING_SLOTS", BusySlots())
    response = post_process(client)
    assert response.status_code == 429
    assert response.json() == {
        "detail": "The processor is busy. Please retry when a job finishes."
    }


def test_end_to_end_upload_processing_and_zip_export(client, monkeypatch):
    monkeypatch.setattr(
        app.core,
        "decode_raw",
        lambda _path, colorspace="srgb": np.full((8, 10, 3), 0.25, dtype=np.float32),
    )
    monkeypatch.setattr(app.core, "copy_metadata", lambda *_args: True)

    response = post_process(client)
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    status = None
    for _ in range(200):
        status_response = client.get(f"/api/jobs/{job_id}")
        assert status_response.status_code == 200
        status = status_response.json()
        if status["status"] in {"done", "failed"}:
            break
        time.sleep(0.01)

    assert status is not None
    assert status["status"] == "done", status
    assert status["progress"] == 100
    assert len(status["outputs"]) == 1
    output = status["outputs"][0]
    assert output["filename"] == "sample.nef"
    assert output["metadata_preserved"] is True

    jpeg = client.get(output["download_jpeg"])
    assert jpeg.status_code == 200
    assert jpeg.headers["content-type"].startswith("image/jpeg")

    tiff = client.get(output["download_tiff"])
    assert tiff.status_code == 200
    assert tiff.headers["content-type"].startswith("image/tiff")

    archive = client.get(f"/files/{job_id}/all.zip")
    assert archive.status_code == 200
    assert archive.headers["content-type"] == "application/zip"
    assert len(archive.content) > 0
