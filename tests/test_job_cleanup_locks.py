from __future__ import annotations

import threading
import time

import jobs


def test_cleanup_releases_per_job_output_lock_entry(tmp_path):
    job = jobs.create_job()
    job_dir = tmp_path / job.id
    job_dir.mkdir()
    jobs.update_job(job.id, status=jobs.JobStatus.DONE)
    now = time.time()
    jobs.output_lock(job.id)

    with jobs._lock:
        jobs._jobs[job.id].finished_at = now - 120
        assert job.id in jobs._output_locks

    removed = jobs._cleanup_once(tmp_path, max_age=60, now=now)

    assert job.id in removed
    with jobs._lock:
        assert job.id not in jobs._jobs
        assert job.id not in jobs._output_locks
    assert not job_dir.exists()


def test_cleanup_waits_for_inflight_output_operation(tmp_path):
    job = jobs.create_job()
    job_dir = tmp_path / job.id
    job_dir.mkdir()
    jobs.update_job(job.id, status=jobs.JobStatus.DONE)
    now = time.time()

    with jobs._lock:
        jobs._jobs[job.id].finished_at = now - 120
    job_lock = jobs.output_lock(job.id)
    cleanup_started = threading.Event()
    cleanup_finished = threading.Event()

    def cleanup():
        cleanup_started.set()
        jobs._cleanup_once(tmp_path, max_age=60, now=now)
        cleanup_finished.set()

    with job_lock:
        worker = threading.Thread(target=cleanup)
        worker.start()
        assert cleanup_started.wait(timeout=2)
        time.sleep(0.05)
        assert not cleanup_finished.is_set()
        assert job_dir.is_dir()

    worker.join(timeout=2)
    assert not worker.is_alive()
    assert cleanup_finished.is_set()
    assert jobs.get_job(job.id) is None
    assert not job_dir.exists()
    with jobs._lock:
        assert job.id not in jobs._output_locks
