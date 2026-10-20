"""Thread-safe job state and terminal-job cleanup."""
from __future__ import annotations

import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class JobStatus(str, Enum):
    QUEUED = "queued"
    DECODING = "decoding"
    APPLYING = "applying"
    SAVING = "saving"
    DONE = "done"
    FAILED = "failed"


_TERMINAL_STATUSES = {JobStatus.DONE, JobStatus.FAILED}


@dataclass
class JobState:
    id: str
    status: JobStatus = JobStatus.QUEUED
    progress: int = 0
    current_file: str = ""
    total_files: int = 0
    done_files: int = 0
    message: str = ""
    outputs: list[dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None


_jobs: dict[str, JobState] = {}
_lock = threading.Lock()


def create_job() -> JobState:
    job = JobState(id=uuid.uuid4().hex)
    with _lock:
        _jobs[job.id] = job
    return job


def get_job(job_id: str) -> JobState | None:
    with _lock:
        return _jobs.get(job_id)


def update_job(job_id: str, **kwargs) -> None:
    with _lock:
        state = _jobs.get(job_id)
        if state is None:
            return

        for key, value in kwargs.items():
            setattr(state, key, value)

        if state.status in _TERMINAL_STATUSES:
            if state.finished_at is None:
                state.finished_at = time.time()
        else:
            state.finished_at = None


def _cleanup_once(work_dir: Path, max_age: int, now: float | None = None) -> list[str]:
    """Remove only completed/failed jobs whose retention period has elapsed.

    Active jobs are never removed just because they have been running longer
    than max_age. Registry entries are removed under the lock before their
    directories are deleted, avoiding a race with status updates.
    """
    now = time.time() if now is None else now
    with _lock:
        expired = [
            job_id
            for job_id, state in _jobs.items()
            if state.status in _TERMINAL_STATUSES
            and state.finished_at is not None
            and now - state.finished_at > max_age
        ]
        for job_id in expired:
            _jobs.pop(job_id, None)

    for job_id in expired:
        shutil.rmtree(work_dir / job_id, ignore_errors=True)
    return expired


def _cleanup_loop(work_dir: Path, max_age: int, interval: int) -> None:
    while True:
        time.sleep(interval)
        _cleanup_once(work_dir, max_age)


def start_cleanup(work_dir: Path, max_age: int = 3600, interval: int = 600) -> None:
    """Start the daemon cleanup thread (default: terminal jobs retained for 1 hour)."""
    if max_age <= 0 or interval <= 0:
        raise ValueError("max_age and interval must be positive")
    t = threading.Thread(
        target=_cleanup_loop,
        args=(work_dir, max_age, interval),
        daemon=True,
        name="photolut-job-cleanup",
    )
    t.start()
