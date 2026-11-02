from pathlib import Path

import numpy as np
import pytest

import hdr_photo


def test_srgb_round_trip():
    values = np.array([0.0, 0.003, 0.04, 0.18, 0.5, 1.0], dtype=np.float32)
    restored = hdr_photo._linear_to_srgb(hdr_photo._srgb_to_linear(values))
    np.testing.assert_allclose(restored, values, atol=1e-6)


def test_inverse_tone_map_preserves_shadows_and_expands_highlights():
    source = np.array([[[0.1, 0.1, 0.1], [0.9, 0.9, 0.9]]], dtype=np.float32)
    hdr = hdr_photo._make_hdr_intent(source, 4.0)
    np.testing.assert_allclose(hdr[0, 0], source[0, 0])
    assert np.all(hdr[0, 1] > source[0, 1])
    assert np.max(hdr) <= 4.0


@pytest.mark.parametrize("boost", [1.0, 0.5, 8.1, float("nan")])
def test_rejects_invalid_boost(boost):
    with pytest.raises(ValueError):
        hdr_photo._make_hdr_intent(np.zeros((1, 1, 3), dtype=np.float32), boost)


def test_export_requires_encoder(tmp_path: Path, monkeypatch):
    source = tmp_path / "input.tiff"
    source.write_bytes(b"not a tiff")
    monkeypatch.setattr(hdr_photo.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="not installed"):
        hdr_photo.export_ultrahdr(source, tmp_path / "output.jpg")
