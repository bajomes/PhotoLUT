from __future__ import annotations

import shutil
import threading
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import tifffile
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

import core
import jobs

BASE_DIR = Path(__file__).resolve().parent
WORK_DIR = BASE_DIR / "jobs"
WORK_DIR.mkdir(parents=True, exist_ok=True)

MAX_RAW_BYTES = 200 * 1024 * 1024
MAX_CUBE_BYTES = 10 * 1024 * 1024
RAW_EXTENSIONS = {
    ".cr2", ".cr3", ".nef", ".arw", ".srf", ".sr2",
    ".dng", ".orf", ".rw2", ".raf", ".pef", ".3fr",
}
PREVIEW_MAX_SIDE = 1600


@asynccontextmanager
async def lifespan(app: FastAPI):
    jobs.start_cleanup(WORK_DIR)
    yield


app = FastAPI(title="LUTPhoto", lifespan=lifespan)


async def _save_upload(upload: UploadFile, dest: Path, max_bytes: int) -> None:
    size = 0
    with dest.open("wb") as f:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                raise HTTPException(413, f"{upload.filename} terlalu besar")
            f.write(chunk)


def _save_outputs(graded: np.ndarray, before: np.ndarray,
                  out_dir: Path, stem: str, idx: int,
                  raw_path: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    suffix = f"_{idx:03d}"

    tiff16 = (graded * 65535.0).round().astype(np.uint16)
    paths["tiff"] = out_dir / f"{stem}{suffix}_lut.tiff"
    tifffile.imwrite(paths["tiff"], tiff16, photometric="rgb", compression="deflate")

    core.copy_exif_to_tiff(raw_path, paths["tiff"])

    jpeg8 = (graded * 255.0).round().astype(np.uint8)
    paths["jpeg"] = out_dir / f"{stem}{suffix}_lut.jpg"
    exif_data = core.extract_exif(raw_path)
    core.save_with_exif(
        Image.fromarray(jpeg8, "RGB"),
        paths["jpeg"],
        exif_data,
        quality=95
    )

    before8 = (before * 255.0).round().astype(np.uint8)
    before_img = Image.fromarray(before8, "RGB")
    after_img = Image.fromarray(jpeg8, "RGB")
    scale = min(1.0, PREVIEW_MAX_SIDE / max(before_img.size))
    if scale < 1.0:
        size = (max(1, int(before_img.width * scale)),
                max(1, int(before_img.height * scale)))
        before_img = before_img.resize(size, Image.LANCZOS)
        after_img = after_img.resize(size, Image.LANCZOS)
    paths["preview_before"] = out_dir / f"preview_before{suffix}.jpg"
    paths["preview_after"] = out_dir / f"preview_after{suffix}.jpg"
    before_img.save(paths["preview_before"], quality=88)
    after_img.save(paths["preview_after"], quality=88)
    return paths


def _process_job_sync(job_id: str, raw_paths: list[Path],
                      cube_path: Path, job_dir: Path,
                      colorspace: str, intensity: float) -> None:
    try:
        jobs.update_job(job_id, status=jobs.JobStatus.DECODING,
                        total_files=len(raw_paths))
        lut = core.parse_cube(cube_path)

        out_dir = job_dir / "out"
        out_dir.mkdir(parents=True, exist_ok=True)

        outputs: list[dict] = []
        for i, raw_path in enumerate(raw_paths):
            jobs.update_job(job_id,
                            status=jobs.JobStatus.DECODING,
                            current_file=raw_path.name,
                            done_files=i,
                            progress=int((i / len(raw_paths)) * 100))

            image = core.decode_raw(raw_path, colorspace=colorspace)

            jobs.update_job(job_id, status=jobs.JobStatus.APPLYING)
            graded = core.apply_lut(image, lut)
            if intensity < 1.0:
                graded = core.blend_intensity(graded, image, intensity)

            jobs.update_job(job_id, status=jobs.JobStatus.SAVING)
            paths = _save_outputs(graded, image, out_dir, raw_path.stem, i, raw_path)

            outputs.append({
                "filename": raw_path.name,
                "preview_before": f"/files/{job_id}/{paths['preview_before'].name}",
                "preview_after": f"/files/{job_id}/{paths['preview_after'].name}",
                "download_tiff": f"/files/{job_id}/{paths['tiff'].name}",
                "download_jpeg": f"/files/{job_id}/{paths['jpeg'].name}",
            })

        jobs.update_job(job_id,
                        status=jobs.JobStatus.DONE,
                        progress=100,
                        done_files=len(raw_paths),
                        outputs=outputs)
    except Exception as e:
        jobs.update_job(job_id, status=jobs.JobStatus.FAILED, message=str(e))


@app.post("/api/process")
async def process(raw_files: list[UploadFile], cube: UploadFile,
                  colorspace: str = Form("srgb"),
                  intensity: float = Form(1.0)) -> dict:
    if not raw_files:
        raise HTTPException(400, "At least one RAW file required")
    if not (cube.filename or "").lower().endswith(".cube"):
        raise HTTPException(400, "LUT file must be .cube format")
    if colorspace not in ("srgb", "log"):
        raise HTTPException(400, "Invalid colorspace")
    if not (0.0 <= intensity <= 1.0):
        raise HTTPException(400, "Intensity must be between 0.0 and 1.0")

    raw_exts: list[str] = []
    for raw in raw_files:
        ext = Path(raw.filename or "").suffix.lower()
        if ext not in RAW_EXTENSIONS:
            raise HTTPException(400, f"Unsupported RAW format: {ext or '(no extension)'}")
        raw_exts.append(ext)

    job = jobs.create_job()
    job_dir = WORK_DIR / job.id
    job_dir.mkdir(parents=True, exist_ok=True)

    cube_path = job_dir / "input.cube"
    raw_paths: list[Path] = []
    try:
        await _save_upload(cube, cube_path, MAX_CUBE_BYTES)
        for i, (raw, ext) in enumerate(zip(raw_files, raw_exts)):
            p = job_dir / f"input_{i}{ext}"
            await _save_upload(raw, p, MAX_RAW_BYTES)
            raw_paths.append(p)
    except HTTPException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(422, f"Failed to save uploads: {e}")

    threading.Thread(
        target=_process_job_sync,
        args=(job.id, raw_paths, cube_path, job_dir, colorspace, intensity),
        daemon=True,
    ).start()

    return {"job_id": job.id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    if not job_id.isalnum():
        raise HTTPException(400, "ID tidak valid")
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job tidak ditemukan")
    return {
        "id": job.id,
        "status": job.status.value,
        "progress": job.progress,
        "current_file": job.current_file,
        "total_files": job.total_files,
        "done_files": job.done_files,
        "message": job.message,
        "outputs": job.outputs,
    }


@app.get("/files/{job_id}/all.zip")
def download_zip(job_id: str) -> FileResponse:
    if not job_id.isalnum():
        raise HTTPException(400, "ID tidak valid")
    job = jobs.get_job(job_id)
    if not job or job.status != jobs.JobStatus.DONE:
        raise HTTPException(404, "Job belum siap")

    out_dir = (WORK_DIR / job_id / "out").resolve()
    zip_path = out_dir / "all.zip"

    if not zip_path.exists():
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for output in job.outputs:
                for key in ("tiff", "jpeg"):
                    url = output[f"download_{key}"]
                    name = Path(url).name
                    path = out_dir / name
                    if path.exists():
                        zf.write(path, name)

    return FileResponse(zip_path, filename="lutphoto_results.zip",
                        media_type="application/zip")


@app.get("/files/{job_id}/{name}")
def get_file(job_id: str, name: str) -> FileResponse:
    if not job_id.isalnum() or ".." in name or "/" in name:
        raise HTTPException(400, "Permintaan tidak valid")
    out_dir = (WORK_DIR / job_id / "out").resolve()
    path = (out_dir / name).resolve()
    if path.parent != out_dir or not path.is_file():
        raise HTTPException(404, "Berkas tidak ditemukan")
    return FileResponse(path, filename=name)


app.mount("/", StaticFiles(directory=BASE_DIR / "static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)