# PhotoLUT 1.1.0 — CI verification addendum

Date: 2026-11-08  
Candidate branch: `release/1.1.0-scope-and-acceptance`  
Verified branch HEAD: `89107d01730ff0e386c7254803f30d1ad240ef85`  
Application-source candidate: `d3ce6c81c28fc7e909515733cfc5cf28c7212aa2`  
Latest CI run: [#42451056317](https://github.com/bajomes/PhotoLUT/actions/runs/42451056317)

## Latest hosted CI result

Run #42452630508 completed successfully on GitHub-hosted Ubuntu 24.04 / Python 3.12.16.

| Job | Job ID | Result | Verified work |
|---|---:|---|---|
| Python and integration | 128644952110 | **LULUS** | Locked dependency install, `pip check`, pinned RAW fixtures and Canon SHA-256, `compileall`, pytest |
| Docker/UI/API smoke | 128644952315 | **LULUS** | CPU/NVIDIA Compose validation, `photo` and `video` builds, photo image excludes FFmpeg and imports app, video image runs non-root, UI/API/OpenAPI checks, JavaScript syntax check, Playwright browser export smoke |

The Python job reports **122 passed, 1 skipped, 0 failed in 69.98 s**. The skipped test is `tests/test_video_integration.py:79`: the hosted runner FFmpeg build lacks the libplacebo custom `.cube` LUT option required by the GPU video integration. This is **TERHAMBAT**, not a pass.

The Docker job's Playwright smoke command was `python tests/browser_export_smoke.py`; it completed successfully against the video-capable image. This is a UI/browser test with mocked API responses, not a real RAW/LUT export or GPU video test.

## Additional local browser smoke evidence

The user ran the candidate image separately to avoid the pre-existing PhotoLUT service on port 8000:

- Started `photolut:ci-video` as `photolut-browser-smoke` on `127.0.0.1:8002`.
- Confirmed the container served the homepage.
- Created a temporary copy of `tests/browser_export_smoke.py` under `/tmp`, changing only its base URL from port 8000 to 8002; the repository test file was not edited.
- Ran the temporary test copy with local Python 3.14.9; exit code **0**.
- Stopped only `photolut-browser-smoke`. The pre-existing `photolut-lutphoto-1` service on port 8000 was not stopped or changed.

Host OS and hardware details were not included in the supplied terminal output. This local evidence verifies the candidate image's mocked UI export flow, not its RAW/LUT processing fidelity.

## Remaining acceptance gates

| Gate | Status | Evidence / minimum closure action |
|---|---|---|
| Core automated photo tests | **LULUS** | Run #42452630508: 122 passed, 1 skipped, 0 failed; three pinned RAW fixtures |
| Docker photo/video image build and smoke | **LULUS** | Run #42451056317, job 128640176289; both targets built and smoke-tested |
| Local candidate browser export smoke | **LULUS** | User-run temporary port-8002 test; exit code 0 |
| 24 MP performance target | **TERHAMBAT** | Run `scripts/benchmark_photo.py` three times on the declared 8-physical-core / 32-GB / NVMe reference host; target ≤120 s/photo and ≤4 GiB peak RSS |
| Calibrated-display review | **BELUM DIJALANKAN** | Record display model, calibration/profile, viewing conditions and reviewer result |
| Dependency reproducibility | **GAGAL** | Runtime/dev locks lack hashes; add hash-verified artifacts and test clean install with `--require-hashes` |
| Docker/system reproducibility | **GAGAL** | Pin Python base image digest and Debian package repository snapshot/version set; rebuild from clean cache |
| Third-party license inventory | **BELUM DIJALANKAN** | Generate and review complete direct/transitive dependency license report for Python and OS packages |
| Physical NVIDIA video integration | **TERHAMBAT** | Execute HLG identity/creative LUT tests on supported NVIDIA hardware with NVDEC, Vulkan/libplacebo and NVENC |
| Public multi-user deployment | **TERHAMBAT** | Not supported by the current single-worker, process-local job registry and loopback-only trust model; do not expose publicly without authentication, ownership and shared state |

## Scope and architecture contract

Gate A remains the local, single-worker RAW photo batch workflow: supported RAW import/validation; 3D `.cube` LUT; 0–100% intensity; preview/before-after; reset/new batch; JPEG and RGB 16-bit TIFF export with sRGB ICC; result deletion; progress/actionable errors; retention warning.

Photo decode and LUT processing run on CPU. The optional video target is a separate HLG/BT.2020 GPU workflow and is not required for Gate A. Undo/redo, general parametric editing, crop/rotate, alpha, camera-Log/HDR still grading, persistent project recovery and video timeline/audio editing remain outside this release.

Lightroom, Snapseed, DaVinci Resolve and Kdenlive are workflow-quality references only. No full-product parity claim is made; Gate B has not been contracted.

## Release decision

**Gate A: BELUM SIAP untuk pengujian penerimaan pengguna.** Core automated tests, both Docker targets, hosted Playwright smoke and the user's isolated local browser smoke passed. The performance, calibrated visual, reproducibility and license gates remain open. No physical NVIDIA GPU test is claimed.

PR #64 remains draft and unmerged. No release has been published.


## Follow-up CI evidence — run #42452630508

The exact Python job log confirms **122 passed, 1 skipped, 0 failed in 69.98 s**. The skip is the optional physical-GPU video integration at `tests/test_video_integration.py:79`, because the hosted FFmpeg lacks libplacebo custom `.cube` LUT support. The job downloaded two Nikon NEF fixtures and a Canon 5D Mark IV CR2 fixture with SHA-256 verification, ran `compileall`, and ran `pytest -q -rs`.

Docker/UI job completed successfully: Compose CPU/NVIDIA validation; photo and video builds; FFmpeg exclusion from photo image; app import; non-root video container; UI/API/OpenAPI smoke; inline JS syntax; browser export smoke. Browser smoke uses mocked API responses and does not establish real RAW/LUT or physical GPU fidelity.

Gate A remains **BELUM SIAP** pending PERF-02 reference-host benchmark, calibrated-display visual review, hash-verified Python dependencies, immutable base/system package snapshot, and full direct/transitive license inventory. PR #64 remains draft and unmerged.
