from __future__ import annotations

import os
import time

import jobs


def _set_dir_mtime(path, mtime: float) -> None:
    os.utime(path, (mtime, mtime))


def test_old_active_job_is_not_cleaned(tmp_path):
    job = jobs.create_job()
    job_dir = tmp_path / job.id
    job_dir.mkdir()
    now = time.time()

    with jobs._lock:
        jobs._jobs[job.id].created_at = now - 10_000

    try:
        removed = jobs._cleanup_once(tmp_path, max_age=60, now=now)
        assert job.id not in removed
        assert jobs.get_job(job.id) is not None
        assert job_dir.is_dir()
    finally:
        with jobs._lock:
            jobs._jobs.pop(job.id, None)


def test_finished_job_is_cleaned_after_retention(tmp_path):
    job = jobs.create_job()
    job_dir = tmp_path / job.id
    job_dir.mkdir()
    jobs.update_job(job.id, status=jobs.JobStatus.DONE)
    now = time.time()

    with jobs._lock:
        jobs._jobs[job.id].finished_at = now - 120

    removed = jobs._cleanup_once(tmp_path, max_age=60, now=now)

    assert job.id in removed
    assert jobs.get_job(job.id) is None
    assert not job_dir.exists()


def test_status_transition_clears_finished_timestamp():
    job = jobs.create_job()
    try:
        jobs.update_job(job.id, status=jobs.JobStatus.FAILED)
        assert jobs.get_job(job.id).finished_at is not None

        jobs.update_job(job.id, status=jobs.JobStatus.DECODING)
        assert jobs.get_job(job.id).finished_at is None
    finally:
        with jobs._lock:
            jobs._jobs.pop(job.id, None)


def test_orphan_job_dir_is_cleaned_after_retention(tmp_path):
    orphan_id = "0123456789abcdef0123456789abcdef"
    orphan_dir = tmp_path / orphan_id
    orphan_dir.mkdir()
    now = time.time()
    _set_dir_mtime(orphan_dir, now - 3600)

    removed = jobs._cleanup_once(tmp_path, max_age=60, now=now)

    assert orphan_id in removed
    assert not orphan_dir.exists()


def test_fresh_orphan_dir_is_kept(tmp_path):
    # A directory missing from the registry may belong to a job that was
    # registered moments ago; only stale directories are removed.
    orphan_id = "0123456789abcdef0123456789abcdef"
    orphan_dir = tmp_path / orphan_id
    orphan_dir.mkdir()
    now = time.time()
    _set_dir_mtime(orphan_dir, now - 1)

    removed = jobs._cleanup_once(tmp_path, max_age=60, now=now)

    assert orphan_id not in removed
    assert orphan_dir.is_dir()


def test_non_job_entries_in_work_dir_are_ignored(tmp_path):
    unrelated_dir = tmp_path / "important_photos"
    unrelated_dir.mkdir()
    unrelated_file = tmp_path / "notes.txt"
    unrelated_file.write_text("keep me")
    short_hex_dir = tmp_path / "deadbeef"
    short_hex_dir.mkdir()
    now = time.time()
    for entry in (unrelated_dir, short_hex_dir):
        _set_dir_mtime(entry, now - 3600)

    removed = jobs._cleanup_once(tmp_path, max_age=60, now=now)

    assert removed == []
    assert unrelated_dir.is_dir()
    assert unrelated_file.exists()
    assert short_hex_dir.is_dir()


def test_registered_job_dir_is_not_treated_as_orphan(tmp_path):
    job = jobs.create_job()
    job_dir = tmp_path / job.id
    job_dir.mkdir()
    now = time.time()
    _set_dir_mtime(job_dir, now - 3600)

    try:
        removed = jobs._cleanup_once(tmp_path, max_age=60, now=now)
        assert job.id not in removed
        assert job_dir.is_dir()
    finally:
        with jobs._lock:
            jobs._jobs.pop(job.id, None)
