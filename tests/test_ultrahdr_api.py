from pathlib import Path

import numpy as np
import pytest
import tifffile
from fastapi.testclient import TestClient

import app


@pytest.fixture
def client():
    with TestClient(app.app) as test_client:
        yield test_client


def test_ultrahdr_endpoint_rejects_non_tiff(client):
    response = client.post(
        "/api/ultrahdr/export",
        files={"tiff_file": ("photo.jpg", b"not a tiff", "image/jpeg")},
    )
    assert response.status_code == 400


def test_ultrahdr_endpoint_rejects_invalid_quality(client):
    response = client.post(
        "/api/ultrahdr/export",
        files={"tiff_file": ("photo.tiff", b"placeholder", "image/tiff")},
        data={"quality": "0", "max_boost": "4"},
    )
    assert response.status_code == 400


def test_ultrahdr_endpoint_returns_verified_jpeg_and_cleans_temp(client, tmp_path, monkeypatch):
    source = tmp_path / "fixture.tiff"
    tifffile.imwrite(source, np.full((4, 5, 3), 32000, dtype=np.uint16), photometric="rgb")
    captured = {}

    def fake_export(input_path, output_path, **kwargs):
        captured["input_exists"] = input_path.is_file()
        output_path.write_bytes(b"verified jpeg")
        return {"gain_map_verified": True}

    monkeypatch.setattr(app.hdr_photo, "export_ultrahdr", fake_export)
    with source.open("rb") as handle:
        response = client.post(
            "/api/ultrahdr/export",
            files={"tiff_file": ("fixture.tiff", handle, "image/tiff")},
            data={"quality": "92", "max_boost": "3.5"},
        )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["x-photolut-gain-map-verified"] == "true"
    assert response.content == b"verified jpeg"
    assert captured["input_exists"] is True
    assert not Path(response.headers.get("x-unused-temp-path", "/nonexistent")).exists()
