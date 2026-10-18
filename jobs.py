"""Manajemen state job dan thread pembersihan otomatis."""
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
        if job_id in _jobs:
            for k, v in kwargs.items():
                setattr(_jobs[job_id], k, v)


def _cleanup_loop(work_dir: Path, max_age: int, interval: int) -> None:
    while True:
        time.sleep(interval)
        now = time.time()
        to_delete: list[str] = []
        with _lock:
            for jid, state in _jobs.items():
                if now - state.created_at > max_age:
                    to_delete.append(jid)
        for jid in to_delete:
            d = work_dir / jid
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
            with _lock:
                _jobs.pop(jid, None)


def start_cleanup(work_dir: Path, max_age: int = 3600, interval: int = 600) -> None:
    """Mulai thread daemon pembersih. Default: bersihkan job >1 jam tiap 10 menit."""
    t = threading.Thread(target=_cleanup_loop, args=(work_dir, max_age, interval), daemon=True)
    t.start()