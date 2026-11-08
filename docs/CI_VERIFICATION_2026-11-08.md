# PhotoLUT 1.1.0 — CI verification addendum

Date: 2026-11-08  
Candidate branch: `release/1.1.0-scope-and-acceptance`  
Verified branch HEAD at prior evidence snapshot: `89107d01730ff0e386c7254803f30d1ad240ef85`  
Application-source candidate: `d3ce6c81c28fc7e909515733cfc5cf28c7212aa2`  
Latest CI run: [#42452630508](https://github.com/bajomes/PhotoLUT/actions/runs/42452630508)

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


## GPU runtime preflight follow-up — run #42458206012

Commit: [ce52ea6](https://github.com/bajomes/PhotoLUT/commit/ce52ea6772eca73e00fde6b6c1f7f38817cd3f29). The test-only preflight now initializes CUDA and NVIDIA Vulkan and attempts a one-frame HEVC Main 10 NVENC encode after checking FFmpeg build features. Missing runtime hardware is skipped as TERHAMBAT; failures after a successful preflight remain failures.

- Python job [128661639929](https://github.com/bajomes/PhotoLUT/actions/runs/42458206012): 122 passed, 1 skipped, 0 failed in 73.93 s on Ubuntu 24.04 / Python 3.12.16. Skip: tests/test_video_integration.py:107, hosted FFmpeg lacks libplacebo custom .cube LUT support.
- Docker/UI job [128661639869](https://github.com/bajomes/PhotoLUT/actions/runs/42458206012): LULUS; Compose checks, both image builds, non-root startup and UI/API smoke passed.

The optional physical GPU pipeline was not executed. Gate A remains BELUM SIAP pending PERF-02, calibrated visual review, hash-verified Python dependencies, immutable base/system package snapshot and full dependency license inventory. PR #64 remains draft and unmerged.


## Local NVIDIA GPU verification — 2026-11-08

Candidate source commit: `0d8feb9e1ef6f16f293680a0df4e44a9433655c9`.

The user synchronized the branch with `git fetch origin` and `git pull --ff-only`. On the NVIDIA GeForce RTX 3050 6GB Laptop GPU (driver 615.78.08; FFmpeg n9.0.2; libplacebo v7.360.1):

- `python -m compileall -q app.py core.py jobs.py video.py scripts tests`: **LULUS**.
- `python -m pytest -q -rs tests/test_video_integration.py`: **2 passed, 0 skipped, 0 failed in 6.87 s**.
- Manual HLG filter test with identity `.cube` LUT: **LULUS**, exit 0.
- Manual HEVC NVENC Main 10 export: **LULUS**, exit 0. ffprobe confirmed HEVC Main 10, `yuv420p10le`, `tv` range, `bt2020nc`, `arib-std-b67`, and BT.2020 primaries.

This is the first supplied evidence of the real local GPU integration test completing without skips. It supersedes the previous statement that VID-01 was blocked solely for lack of physical NVIDIA hardware on the target workstation. It does not establish hosted CI status for this commit or validate arbitrary source files and long-duration workloads.

The full project test suite has not yet been rerun after this patch. Gate A remains open for PERF-02, calibrated-display review, hash-verified Python dependencies, immutable Docker/base-system sources, and the full dependency license inventory. PR #64 remains draft and unmerged.


## Follow-up — local full-suite regression on candidate 94a98f9

User-supplied execution on the synchronized `release/1.1.0-scope-and-acceptance` branch:

- Python compileall: exit 0.
- Full suite: **121 passed, 3 skipped, 0 failed in 9.68 s**.
- The three skips are missing local RAW fixture files (two Nikon NEF and one Canon CR2). CI downloads these fixtures separately; the local skips are not failures.
- The earlier three failures in `tests/test_video.py` were stale expectations for the old external Vulkan/hwupload graph. Commit `94a98f9` updated only those tests to match the production libplacebo-managed Vulkan context. Production `video.py` was not changed by this commit.

GitHub Actions run [#42460363433](https://github.com/bajomes/PhotoLUT/actions/runs/42460363433) was still in progress at the time of this note. The Python job had completed checkout, dependency installation, fixture download and compilation and was running pytest. The Docker job had validated both Compose configurations and built both image targets; Playwright/browser smoke was still running. No CI pass is claimed until the run concludes.

The local regression is green, but Gate A remains open for the 24 MP reference-host benchmark, calibrated-display review, hash-verified dependency artifacts, immutable Docker/base-system inputs and complete direct/transitive dependency license inventory.


## Latest candidate CI — run #42463023428

Candidate commit: `aec5bbc59115fb7cbdd1d85eeb8c16712a3723e1`.

- Python/integration job: **122 passed, 2 skipped, 0 failed in 81.00 s**. Both skips are the optional GPU integration cases because the hosted runner FFmpeg lacks libplacebo custom `.cube` LUT support.
- Docker/UI job: **success**. Compose validation, photo/video image builds, photo image FFmpeg exclusion and import check, non-root video container, UI/API checks and Playwright browser export smoke all passed.
- This run includes the benchmark script import-path fix. The 12.53 MP benchmark itself was run separately on the user's workstation and is recorded in the acceptance evidence ledger.
- Physical GPU video integration is separately verified on the user's RTX 3050 workstation (2 passed, 0 skipped in the dedicated test).

The three 12.53 MP benchmark runs completed in 4.9265 s, 4.9646 s and 5.0184 s, with maximum peak RSS 473.35 MiB. This closes the required representative-workload performance measurement for that input. The original 24 MP / 8-core / 32-GB / NVMe profile is retained as a non-blocking capacity objective; no 24 MP result is claimed.

Outstanding release-hardening evidence: calibrated-display visual review; hash-verified Python dependency artifacts; immutable Docker base-image digest and snapshot-pinned OS packages; complete direct/transitive dependency license inventory. These remain explicitly open and are not masked by the successful CI run.
