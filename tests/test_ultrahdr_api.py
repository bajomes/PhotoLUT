from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app


@pytest.fixture
def client():
    return TestClient(app.app)


def test_ultrahdr_api_rejects_non_tiff(client):
    response = client.post(
        "/api/ultrahdr/export",
        files={"tiff_file": ("photo.png", b"not a tiff", "image/png")},
    )
    assert response.status_code == 400


@pytest.mark.parametrize("data", [
    {"quality": "0"},
    {"quality": "101"},
    {"max_boost": "1"},
    {"max_boost": "8.1"},
])
def test_ultrahdr_api_rejects_invalid_options(client, data):
    response = client.post(
        "/api/ultrahdr/export",
        files={"tiff_file": ("photo.tiff", b"placeholder", "image/tiff")},
        data=data,
    )
    assert response.status_code == 422


def test_ultrahdr_api_returns_verified_jpeg_and_cleans_temp_files(
    client, tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(app, "WORK_DIR", tmp_path)

    def fake_export(source, destination, *, quality, max_boost):
        assert source.read_bytes() == b"tiff-fixture"
        assert quality == 92
        assert max_boost == 3.5
        destination.write_bytes(b"jpeg-ultrahdr-fixture")
        return {"gain_map_verified": True}

    monkeypatch.setattr(app.hdr_photo, "export_ultrahdr", fake_export)
    response = client.post(
        "/api/ultrahdr/export",
        files={"tiff_file": ("landscape.tiff", b"tiff-fixture", "image/tiff")},
        data={"quality": "92", "max_boost": "3.5"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["x-photolut-gain-map-verified"] == "true"
    assert response.content == b"jpeg-ultrahdr-fixture"
    assert not list(tmp_path.glob("photolut-ultrahdr-*"))



def test_ultrahdr_api_maps_encoder_timeout_to_gateway_timeout(
    client, tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(app, "WORK_DIR", tmp_path)

    def timed_out(*_args, **_kwargs):
        raise RuntimeError("Ultra HDR encoding timed out")

    monkeypatch.setattr(app.hdr_photo, "export_ultrahdr", timed_out)
    response = client.post(
        "/api/ultrahdr/export",
        files={"tiff_file": ("landscape.tiff", b"tiff-fixture", "image/tiff")},
    )
    assert response.status_code == 504
    assert not list(tmp_path.glob("photolut-ultrahdr-*"))


def test_ultrahdr_api_releases_slot_when_job_directory_creation_fails(
    client, monkeypatch
):
    import threading

    semaphore = threading.BoundedSemaphore(1)
    monkeypatch.setattr(app, "PROCESSING_SLOTS", semaphore)

    def fail_mkdtemp(*_args, **_kwargs):
        raise OSError("work directory is unavailable")

    monkeypatch.setattr(app.tempfile, "mkdtemp", fail_mkdtemp)
    response = client.post(
        "/api/ultrahdr/export",
        files={"tiff_file": ("landscape.tiff", b"tiff-fixture", "image/tiff")},
    )
    assert response.status_code == 500
    assert semaphore.acquire(blocking=False)
    semaphore.release()


def test_ultrahdr_api_rejects_malformed_tiff(client, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(app, "WORK_DIR", tmp_path)
    monkeypatch.setattr(app.hdr_photo.shutil, "which", lambda _: "/usr/bin/ultrahdr_app")
    response = client.post(
        "/api/ultrahdr/export",
        files={"tiff_file": ("photo.tiff", b"not a TIFF file", "image/tiff")},
    )
    assert response.status_code == 422
    assert "readable TIFF" in response.json()["detail"]
    assert not list(tmp_path.glob("photolut-ultrahdr-*"))
