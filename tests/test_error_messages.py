"""Regression tests for translated backend error messages.

Each test pins the (HTTP status, detail) pair for one error path in app.py.
Registry and filesystem state are controlled via monkeypatch so results never
depend on jobs or files that happen to exist in the environment.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app as app_module
import jobs
from jobs import JobState, JobStatus

UNUSED_JOB_ID = "11111111111111111111111111111111"

@pytest.fixture()
def client():
    return TestClient(app_module.app)

class TestJobStatusErrors:
    def test_invalid_job_id_format(self, client):
        response = client.get("/api/jobs/not-alnum-id")
        assert response.status_code == 400
        assert response.json() == {"detail": "Invalid job ID"}

    def test_job_not_found(self, client, monkeypatch):
        monkeypatch.setattr(jobs, "get_job", lambda job_id: None)
        response = client.get(f"/api/jobs/{UNUSED_JOB_ID}")
        assert response.status_code == 404
        assert response.json() == {"detail": "Job not found"}

class TestDownloadZipErrors:
    def test_invalid_job_id_format(self, client):
        response = client.get("/files/not-alnum-id/all.zip")
        assert response.status_code == 400
        assert response.json() == {"detail": "Invalid job ID"}

    def test_job_not_ready(self, client, monkeypatch):
        running = JobState(id=UNUSED_JOB_ID, status=JobStatus.SAVING)
        monkeypatch.setattr(jobs, "get_job", lambda job_id: running)
        response = client.get(f"/files/{UNUSED_JOB_ID}/all.zip")
        assert response.status_code == 404
        assert response.json() == {"detail": "Job results are not ready yet"}

class TestGetFileErrors:
    def test_invalid_job_id_format(self, client):
        response = client.get("/files/not-alnum-id/preview.jpg")
        assert response.status_code == 400
        assert response.json() == {"detail": "Invalid request"}

    def test_name_containing_double_dots(self, client):
        response = client.get(f"/files/{UNUSED_JOB_ID}/foo..jpg")
        assert response.status_code == 400
        assert response.json() == {"detail": "Invalid request"}

    def test_name_containing_slash_calls_handler_directly(self):
        with pytest.raises(HTTPException) as excinfo:
            app_module.get_file(UNUSED_JOB_ID, "foo/bar.jpg")
        assert excinfo.value.status_code == 400
        assert excinfo.value.detail == "Invalid request"

    def test_file_missing_on_disk(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(app_module, "WORK_DIR", tmp_path)
        response = client.get(f"/files/{UNUSED_JOB_ID}/missing.jpg")
        assert response.status_code == 404
        assert response.json() == {"detail": "File not found"}
