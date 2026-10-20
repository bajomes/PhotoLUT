from __future__ import annotations

import time

import jobs


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
