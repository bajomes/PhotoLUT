from __future__ import annotations

import asyncio

import pytest

import app
import jobs


def test_file_response_releases_lease_when_client_disconnects(tmp_path):
    job = jobs.create_job()
    jobs.update_job(job.id, status=jobs.JobStatus.DONE)
    file_path = tmp_path / "download.bin"
    file_path.write_bytes(b"download payload")
    assert jobs.acquire_output_lease(job.id)

    response = app.LeasedFileResponse(file_path, lease_job_id=job.id)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "method": "GET",
        "headers": [],
    }

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.body":
            raise RuntimeError("client disconnected")

    async def run_response():
        with pytest.raises(RuntimeError, match="client disconnected"):
            await response(scope, receive, send)

    asyncio.run(run_response())
    assert not jobs.has_output_leases(job.id)
