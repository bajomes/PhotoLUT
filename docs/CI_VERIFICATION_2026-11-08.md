# PhotoLUT 1.1.0 — CI verification addendum

Date: 2026-11-08  
Candidate branch: `release/1.1.0-scope-and-acceptance`  
Latest verified HEAD: `2765f796d0ecdfe4c88e7ca308c01a62e4218184`

## CI results

Both CI workflows completed successfully against the latest HEAD:

| Run | Event | Python/integration job | Docker/UI/API smoke job | Overall |
|---|---|---|---|---|
| [#42442777335](https://github.com/bajomes/PhotoLUT/actions/runs/42442777335) | push | success | success | **LULUS** |
| [#42442780026](https://github.com/bajomes/PhotoLUT/actions/runs/42442780026) | pull_request | success | success | **LULUS** |

Earlier documentation commits triggered runs #42442748634 and #42442753469, which were cancelled by the workflow concurrency policy after a newer commit superseded them. They are not counted as failures or passes. The successful runs above supersede them.

The Python job completed dependency installation, pinned RAW fixture download, Python `compileall`, and `pytest -q -rs`. The Docker smoke job completed CPU/NVIDIA Compose configuration validation, image build, Playwright browser installation, container startup, non-root execution check, and UI/API smoke checks.

The job metadata available for this report does not expose the detailed pytest count for HEAD `2765f796...`. The earlier exact-code-commit run #42407685107 reported 122 passed, 1 skipped, 0 failed in 79.30 seconds. Do not transfer that test count to the latest documentation HEAD without its test log.

## Scope of this evidence

The successful runs verify that the latest documentation-only commits do not break the Python test job or Docker/UI/API smoke pipeline. They do not close the following acceptance records:

- **VID-01 — TERHAMBAT:** no physical NVIDIA GPU / compatible driver / NVDEC-Vulkan-libplacebo-NVENC validation in the available runner.
- **PERF-02 — TERHAMBAT:** no reference workstation matching 8 physical CPU cores, 32 GB RAM and NVMe for the predeclared 24 MP RAW benchmark (≤120 s/photo, ≤4 GiB peak RSS).
- **PRE-01 visual review — BELUM DIJALANKAN:** no calibrated-display inspection.
- **DOC-01 license inventory — BELUM DIJALANKAN:** project MIT license is present, but a full direct/transitive dependency license inventory has not been generated.
- **Reproducibility — BELUM DIJALANKAN:** Python locks pin versions but lack artifact hashes; the base image tag is mutable; FFmpeg is installed from Debian Sid without a snapshot pin.

## Additional architecture audit observation

The current `Dockerfile` installs `ffmpeg/sid` and asserts libplacebo custom-LUT, NVENC, CUDA and Vulkan capabilities in the single image used by the default Compose service. This means the default CPU photo image build is coupled to a video/GPU-capable FFmpeg package build even though the required photo pipeline is CPU-only. The current CI proves that this image builds on its hosted runner; it does not prove that the system package set is hermetic or that CPU-only hosts can reproduce the build indefinitely.

Do not split the image by merely deleting the FFmpeg checks: the application imports and optional video routes must first be inspected to establish graceful behavior when FFmpeg or GPU capabilities are absent. A safe follow-up is a separately tested CPU photo image and opt-in video image, with Compose and CI covering both, after that dependency audit.

## Release decision

**Gate A remains NOT READY for user acceptance.** The latest HEAD has green CI, but green CI does not close the hardware benchmark, calibrated visual review, full license audit, or system-image reproducibility requirements. PR #64 remains draft and unmerged.
