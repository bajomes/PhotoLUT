from __future__ import annotations

import os
import re
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
MAX_TOTAL_UPLOAD_BYTES = 512 * 1024 * 1024
MAX_RAW_FILES = 20


def _processing_capacity_from_env() -> int:
    """Default to one heavy RAW job; allow at most two concurrent jobs."""
    raw_value = os.environ.get("PHOTOLUT_CONCURRENCY", "1")
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError("PHOTOLUT_CONCURRENCY must be 1 or 2") from exc
    if value not in (1, 2):
        raise RuntimeError("PHOTOLUT_CONCURRENCY must be 1 or 2")
    return value


PROCESSING_SLOTS = threading.BoundedSemaphore(value=_processing_capacity_from_env())
RAW_EXTENSIONS = {
    ".cr2", ".cr3", ".nef", ".arw", ".srf", ".sr2",
    ".dng", ".orf", ".rw2", ".raf", ".pef", ".3fr",
}
PREVIEW_MAX_SIDE = 1600


@asynccontextmanager
async def lifespan(app: FastAPI):
    jobs.start_cleanup(WORK_DIR)
    yield


app = FastAPI(title="PhotoLUT", description="Apply 3D .cube LUTs to RAW photos locally.", lifespan=lifespan)


async def _save_upload(
    upload: UploadFile,
    dest: Path,
    max_bytes: int,
    remaining_total_bytes: int,
) -> int:
    size = 0
    with dest.open("wb") as f:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                raise HTTPException(413, f"{upload.filename or 'Upload'} exceeds its size limit")
            if size > remaining_total_bytes:
                raise HTTPException(413, "Batch exceeds the 512 MiB total upload limit")
            f.write(chunk)
    return size


def _quantize_rows(
    image: np.ndarray,
    maximum: int,
    dtype: np.dtype,
    rows_per_chunk: int = 128,
) -> np.ndarray:
    """Quantize RGB float pixels in row chunks to avoid full-frame float temporaries."""
    if rows_per_chunk < 1:
        raise ValueError("rows_per_chunk must be positive")
    output = np.empty(image.shape, dtype=dtype)
    scale = np.float32(maximum)
    for y0 in range(0, image.shape[0], rows_per_chunk):
        y1 = min(y0 + rows_per_chunk, image.shape[0])
        quantized = np.rint(image[y0:y1] * scale).astype(dtype)
        output[y0:y1] = quantized
    return output


def _save_outputs(
    graded: np.ndarray,
    before: np.ndarray,
    out_dir: Path,
    stem: str,
    idx: int,
    raw_path: Path,
) -> tuple[dict[str, Path], bool]:
    paths: dict[str, Path] = {}
    suffix = f"_{idx:03d}"
    icc_profile = core.srgb_icc_profile()

    # Quantize the TIFF output in small row groups; preserve round-to-nearest
    # semantics while avoiding one or more full-resolution float temporaries.
    paths["tiff"] = out_dir / f"{stem}{suffix}_lut.tiff"
    tiff16 = _quantize_rows(graded, 65535, np.uint16)
    extratags = [(34675, "B", len(icc_profile), icc_profile, False)]
    tifffile.imwrite(
        paths["tiff"], tiff16, photometric="rgb", compression="deflate",
        extratags=extratags,
    )
    del tiff16
    tiff_metadata_ok = core.copy_metadata(raw_path, paths["tiff"])

    # Create and persist each JPEG/preview in turn so the full-size before,
    # after, and 16-bit buffers are not all resident at once.
    paths["jpeg"] = out_dir / f"{stem}{suffix}_lut.jpg"
    jpeg8 = _quantize_rows(graded, 255, np.uint8)
    Image.fromarray(jpeg8, "RGB").save(
        paths["jpeg"], quality=95, icc_profile=icc_profile,
    )
    jpeg_metadata_ok = core.copy_metadata(raw_path, paths["jpeg"])

    before_img = Image.fromarray(jpeg8, "RGB")
    scale = min(1.0, PREVIEW_MAX_SIDE / max(before_img.size))
    if scale < 1.0:
        size = (max(1, int(before_img.width * scale)),
                max(1, int(before_img.height * scale)))
        before_img = before_img.resize(size, Image.LANCZOS)
    paths["preview_after"] = out_dir / f"preview_after{suffix}.jpg"
    before_img.save(paths["preview_after"], quality=88, icc_profile=icc_profile)
    del before_img, jpeg8

    before8 = _quantize_rows(before, 255, np.uint8)
    before_img = Image.fromarray(before8, "RGB")
    scale = min(1.0, PREVIEW_MAX_SIDE / max(before_img.size))
    if scale < 1.0:
        size = (max(1, int(before_img.width * scale)),
                max(1, int(before_img.height * scale)))
        before_img = before_img.resize(size, Image.LANCZOS)
    paths["preview_before"] = out_dir / f"preview_before{suffix}.jpg"
    before_img.save(paths["preview_before"], quality=88, icc_profile=icc_profile)
    del before_img, before8

    return paths, tiff_metadata_ok and jpeg_metadata_ok

def _safe_output_stem(filename: str) -> str:
    """Return a portable filename stem without path components or unsafe characters."""
    basename = filename.replace(chr(92), "/").rsplit("/", 1)[-1]
    stem = Path(basename).stem
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", stem).strip("._-")
    return (safe or "photo")[:80]


def _run_job_with_slot(*args) -> None:
    try:
        _process_job_sync(*args)
    finally:
        PROCESSING_SLOTS.release()


def _process_job_sync(
    job_id: str,
    raw_paths: list[Path],
    original_filenames: list[str],
    cube_path: Path,
    job_dir: Path,
    colorspace: str,
    intensity: float,
) -> None:
    try:
        jobs.update_job(job_id, status=jobs.JobStatus.DECODING,
                        total_files=len(raw_paths))
        lut = core.parse_cube(cube_path)

        out_dir = job_dir / "out"
        out_dir.mkdir(parents=True, exist_ok=True)

        outputs: list[dict] = []
        for i, raw_path in enumerate(raw_paths):
            original_filename = original_filenames[i]
            output_stem = _safe_output_stem(original_filename)
            jobs.update_job(job_id,
                            status=jobs.JobStatus.DECODING,
                            current_file=original_filename,
                            done_files=i,
                            progress=int((i / len(raw_paths)) * 100))

            image = core.decode_raw(raw_path, colorspace=colorspace)

            jobs.update_job(job_id, status=jobs.JobStatus.APPLYING)
            graded = core.apply_lut(image, lut)
            if intensity < 1.0:
                graded = core.blend_intensity(graded, image, intensity)

            jobs.update_job(job_id, status=jobs.JobStatus.SAVING)
            paths, metadata_ok = _save_outputs(
                graded, image, out_dir, output_stem, i, raw_path
            )

            outputs.append({
                "filename": original_filename,
                "metadata_preserved": metadata_ok,
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
        raise HTTPException(400, "At least one RAW file is required")
    if len(raw_files) > MAX_RAW_FILES:
        raise HTTPException(413, f"A batch can contain at most {MAX_RAW_FILES} RAW files")
    if not (cube.filename or "").lower().endswith(".cube"):
        raise HTTPException(400, "LUT file must be .cube format")
    if colorspace != "srgb":
        raise HTTPException(
            400,
            "Only sRGB input is supported currently. Camera Log LUTs need "
            "a camera-specific transfer-function and gamut transform.",
        )
    if not (0.0 <= intensity <= 1.0):
        raise HTTPException(400, "Intensity must be between 0.0 and 1.0")

    raw_exts: list[str] = []
    for raw in raw_files:
        ext = Path(raw.filename or "").suffix.lower()
        if ext not in RAW_EXTENSIONS:
            raise HTTPException(400, f"Unsupported RAW format: {ext or '(no extension)'}")
        raw_exts.append(ext)

    if not PROCESSING_SLOTS.acquire(blocking=False):
        raise HTTPException(429, "The processor is busy. Please retry when a job finishes.")

    job = jobs.create_job()
    job_dir = WORK_DIR / job.id
    try:
        job_dir.mkdir(parents=True, exist_ok=False)
    except Exception as exc:
        jobs.update_job(job.id, status=jobs.JobStatus.FAILED, message="Could not create job directory")
        PROCESSING_SLOTS.release()
        raise HTTPException(500, "Could not create processing job") from exc

    cube_path = job_dir / "input.cube"
    raw_paths: list[Path] = []
    original_filenames: list[str] = []
    try:
        total_uploaded = await _save_upload(
            cube, cube_path, MAX_CUBE_BYTES, MAX_TOTAL_UPLOAD_BYTES
        )
        for i, (raw, ext) in enumerate(zip(raw_files, raw_exts)):
            original = (raw.filename or f"photo_{i + 1}{ext}").replace(chr(92), "/").rsplit("/", 1)[-1]
            p = job_dir / f"input_{i}{ext}"
            uploaded_size = await _save_upload(
                raw, p, MAX_RAW_BYTES, MAX_TOTAL_UPLOAD_BYTES - total_uploaded
            )
            total_uploaded += uploaded_size
            raw_paths.append(p)
            original_filenames.append(original)
    except BaseException as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        jobs.update_job(job.id, status=jobs.JobStatus.FAILED, message="Upload failed")
        PROCESSING_SLOTS.release()
        if isinstance(exc, HTTPException):
            raise
        if isinstance(exc, Exception):
            raise HTTPException(422, "Failed to save uploads") from exc
        raise

    try:
        threading.Thread(
            target=_run_job_with_slot,
            args=(job.id, raw_paths, original_filenames, cube_path, job_dir, colorspace, intensity),
            daemon=True,
            name=f"photolut-{job.id[:8]}",
        ).start()
    except Exception as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        jobs.update_job(job.id, status=jobs.JobStatus.FAILED, message="Could not start processing")
        PROCESSING_SLOTS.release()
        raise HTTPException(500, "Could not start processing job") from exc

    return {"job_id": job.id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    if not job_id.isalnum():
        raise HTTPException(400, "Invalid job ID")
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
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
        raise HTTPException(400, "Invalid job ID")
    job = jobs.get_job(job_id)
    if not job or job.status != jobs.JobStatus.DONE:
        raise HTTPException(404, "Job results are not ready yet")

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
        raise HTTPException(400, "Invalid request")
    out_dir = (WORK_DIR / job_id / "out").resolve()
    path = (out_dir / name).resolve()
    if path.parent != out_dir or not path.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(path, filename=name)


app.mount("/", StaticFiles(directory=BASE_DIR / "static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)