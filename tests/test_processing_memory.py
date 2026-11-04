from __future__ import annotations

import weakref
from pathlib import Path

import numpy as np

import app


def test_batch_releases_previous_full_resolution_buffers_before_next_decode(
    tmp_path, monkeypatch
):
    previous_image = None
    decode_count = 0

    def decode_raw(_path, colorspace="srgb"):
        nonlocal previous_image, decode_count
        if decode_count:
            assert previous_image() is None
        image = np.zeros((8, 8, 3), dtype=np.float32)
        previous_image = weakref.ref(image)
        decode_count += 1
        return image

    def save_outputs(_graded, _before, _out_dir, _stem, _idx, _raw_path):
        return (
            {
                "preview_before": Path("before.jpg"),
                "preview_after": Path("after.jpg"),
                "tiff": Path("output.tiff"),
                "jpeg": Path("output.jpg"),
            },
            True,
        )

    monkeypatch.setattr(app.core, "parse_cube", lambda _path: object())
    monkeypatch.setattr(app.core, "decode_raw", decode_raw)
    monkeypatch.setattr(app.core, "apply_lut", lambda image, _lut: image.copy())
    monkeypatch.setattr(app, "_save_outputs", save_outputs)
    monkeypatch.setattr(app.jobs, "update_job", lambda *_args, **_kwargs: None)

    job_dir = tmp_path / "job"
    job_dir.mkdir()
    app._process_job_sync(
        "job-id",
        [tmp_path / "first.nef", tmp_path / "second.nef"],
        ["first.nef", "second.nef"],
        tmp_path / "look.cube",
        job_dir,
        "srgb",
        1.0,
    )

    assert decode_count == 2
