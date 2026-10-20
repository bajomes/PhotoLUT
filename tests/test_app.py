from __future__ import annotations

import numpy as np
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
