# PhotoLUT 1.1.0 — Release Scope and Acceptance Plan

**Status:** scope baseline for review; acceptance execution is tracked separately.  
**Baseline:** `main` at `babe36b19bd3d4a3da3c9b4e9fcc5bef2e5fb3ad` (2026-11-08).  
**Product boundary:** local Docker-hosted RAW photo batch processor with 3D .cube LUT grading and JPEG/16-bit TIFF delivery. This is not a general photo editor, RAW catalog, or video editor.

## 1. Release scope (frozen before feature expansion)

| Capability | Classification | Release decision and rationale |
|---|---|---|
| Import RAW photographs | **Required** | Core input. Release fixtures certify two Nikon NEF samples and one Canon 5D Mark IV CR2; other listed extensions remain decoder/camera-dependent and are not universally certified. |
| Import 3D `.cube` LUT | **Required** | Core grading input; supported dimensions 2–128, RGB table, DOMAIN_MIN/MAX validation. 1D LUTs and other LUT formats are out of scope. |
| Apply LUT and set intensity 0–100% | **Required** | Core value proposition; trilinear interpolation; intensity blend in linear-light sRGB. |
| Interactive preview and before/after comparison | **Required** | Needed to judge the selected LUT before batch export. Preview is a reduced-resolution JPEG proxy, not a pixel-identical proof of final output. |
| Reset / start a new batch | **Required** | Required to safely reuse the workflow after export. |
| Export JPEG and 16-bit TIFF; download either or both as ZIP | **Required** | Existing advertised output formats. RGB output with embedded sRGB ICC profile. |
| Remove an individual completed result | **Required** | Existing UI capability; must remain safe during concurrent downloads. |
| Loading/progress and actionable errors | **Required** | Existing asynchronous batch job model; API validation, processing status and failure state must be visible. |
| Temporary-result retention warning | **Required** | Job outputs become eligible for cleanup after 30 minutes (cleanup runs every 2 minutes) and are not restored after container recreation; the UI must warn before users lose access. |
| Cooperative cancellation of an active batch | **Optional** | No cancel endpoint exists. A safe implementation would only cancel between RAW files; interrupting an active LibRaw decode/export worker is not supported by the current thread model. |
| Persistent project/session recovery | **Out of release** | PhotoLUT is a temporary batch processor, not a project/catalog manager. Users must download finished outputs; no recovery after container recreation is promised. |
| Undo/redo history | **Out of release** | There is no edit stack or non-destructive project document. Adding history would require a broader editing model, not a safe small release fix. |
| Exposure, contrast, white balance, highlights/shadows, saturation, curves | **Out of release** | Not part of the current LUT-only editing model; would materially expand color pipeline and validation scope. |
| Crop and arbitrary rotate tools | **Out of release** | RAW orientation is normalized by the decoder/export path; user-controlled geometry editing is not implemented. |
| Alpha-channel editing/preservation | **Out of release** | RAW decode and current deliverables are RGB; output contract is RGB JPEG/TIFF. No alpha workflow is advertised. |
| Camera Log, wide-gamut/HDR still-photo grading | **Out of release** | Current photo pipeline explicitly converts RAW to sRGB. A valid camera-specific transfer/gamut transform and color-managed display path are prerequisites. |
| Video HLG/BT.2020 inspection and GPU LUT export | **Optional, separate validation track** | Existing experimental workflow is retained, but does not expand the required photo release. It requires NVIDIA NVDEC/Vulkan/libplacebo/NVENC hardware validation; no CPU fallback is promised. |
| Video timeline, audio editing, codec suite, general video editor | **Out of release** | DaVinci Resolve and Kdenlive are comparison references, not a mandate to reproduce their editing systems. |

No new editing feature or third-party service is approved by this scope baseline.

## 2. Architecture and color contract

1. RAW decode: rawpy/LibRaw → camera white balance → sRGB RGB, 16-bit decode normalized to float32 [0,1], no automatic brightness amplification.
2. LUT: parse a 3D `.cube` RGB table and optional finite DOMAIN_MIN/MAX; red varies fastest in file order; trilinear interpolation over the [blue, green, red] table axes.
3. Intensity: evaluate the LUT, then blend original and graded sRGB values after decoding both to linear-light sRGB; re-encode to sRGB. Intensity 0 and 1 preserve their exact endpoints.
4. Preview: half-size RAW decode to 8-bit sRGB, LUT evaluation, JPEG proxy. Preview is a fast selection aid; resizing, 8-bit quantization and JPEG encoding mean it is not the final export pixel buffer.
5. Export: RGB TIFF quantized to uint16 with round-to-nearest; RGB JPEG quality 95; embed sRGB ICC. Copy descriptive EXIF/XMP/IPTC metadata best-effort, normalize orientation and ColorSpace tags. Metadata failure must be surfaced as a warning.
6. Alpha is not part of this release contract. No claim of RAW GPU acceleration; photo demosaic and LUT processing run on CPU.

## 3. Product comparison matrix (workflow benchmark, not parity claim)

| Reference | Relevant benchmark capability | PhotoLUT evidence today | Gap / acceptance implication |
|---|---|---|---|
| Adobe Lightroom | RAW ingest, color adjustments, preview, before/after and export | rawpy RAW decode, sRGB preview, LUT intensity, compare, JPEG/TIFF export | PhotoLUT is a batch LUT renderer, not a catalog or full parametric editor. Validate supported camera fixtures, output profile and metadata. |
| Snapseed | Direct photo adjustments, crop/rotate, mobile interaction | No mobile app or geometry/parametric editing stack | These functions remain outside this release; no mobile parity claim. |
| DaVinci Resolve | Color-managed video grading, LUT workflow, scopes and delivery | Separate HLG video inspection and NVIDIA GPU LUT export | Optional hardware-specific track only; no timeline, scopes, audio or general video editing parity claim. |
| Kdenlive | Timeline-based editing, media/codec/render workflow | No timeline; only one-shot HLG LUT transcode | Video editing features are explicitly outside this release. |

## 4. Acceptance criteria and test IDs

Status vocabulary is strict: **LULUS** means executed and passed; **GAGAL** means executed and failed; **BELUM DIJALANKAN** means planned/not executed; **TERHAMBAT** means a required environment or asset is unavailable.

| ID | Scenario / input | Expected result and predeclared tolerance | Evidence / current status |
|---|---|---|---|
| IMP-01 | Upload 1–20 RAW files, valid `.cube`, supported sRGB setting | Valid job created; invalid extension, empty/malformed upload and size/count limit rejected with actionable HTTP error | `tests/test_api_validation.py`, `tests/test_app.py`; **LULUS** in CI run #42405436400 (122 tests passed overall) |
| LUT-01 | Identity 2×2×2 and larger LUTs | Identity error max absolute ≤ 1e-6 in float32 synthetic test | `tests/test_core.py`; **LULUS** in CI run #42405436400 |
| LUT-02 | Channel permutation and analytic affine LUT | Trilinear result max absolute ≤ 2e-6 for supported synthetic fixture | `tests/test_core.py`; **LULUS** in CI run #42405436400 |
| LUT-03 | Malformed rows, duplicate/missing size, invalid domain, NaN/Inf, over-limit LUT | Reject before export; no partial success artifact | `tests/test_core.py`, `tests/test_lut_overflow.py`; **LULUS** in CI run #42405436400 |
| INT-01 | Intensity 0, 0.5, 1 | 0 and 1 endpoints array-equal to original/graded; 0.5 blend in linear-light sRGB with max absolute error ≤ 1e-6 against reference | `tests/test_core.py`; **LULUS** in CI run #42405436400 |
| COL-01 | LUT domain clipping and finite image boundaries | Values are clipped to declared LUT domain, output RGB remains finite and in [0,1] | `tests/test_core.py`, `tests/test_memory_footprint.py`; **LULUS** in CI run #42405436400 |
| COL-02 | TIFF export from deterministic RGB float fixture | uint16 RGB samples exactly equal `rint(pixel × 65535)`; embedded sRGB ICC present | `tests/test_raw_integration.py`; **LULUS** in CI run #42405436400 using the pinned Nikon NEF ×2 and Canon CR2 fixtures |
| COL-03 | JPEG export from deterministic RGB fixture | RGB mode, quality 95, embedded sRGB ICC; lossy pixel equality is not asserted | `tests/test_raw_integration.py`; **LULUS** in CI run #42405436400 |
| COL-04 | RAW alpha / TIFF alpha input | Not applicable; RGB-only input/output contract. No alpha preservation claim | Scope contract; **LULUS** as an explicit exclusion |
| PRE-01 | Preview and final export of same RAW/LUT | Same LUT/domain/intensity semantics; no pixel-identical requirement because preview uses half-size decode, 8-bit quantization and JPEG proxy. Compare UI preview against export visually on calibrated display as a separate manual check | `tests/browser_export_smoke.py` black/white 1-pixel fixture verifies 0/50/100% intensity and 50% = sRGB 188; **LULUS** in CI run #42406297351; calibrated-display manual comparison **BELUM DIJALANKAN** |
| UI-01 | Open format picker, Tab/Shift+Tab, wrap, Escape, close, backdrop, keyboard focus recovery | Focus remains in dialog; choices are traversed before close control; focus returns to trigger on close | `tests/browser_export_smoke.py`; **LULUS** in run #42406743222 |
| UI-02 | Select JPEG, TIFF, all; remove result; download during remove | Correct archive content; deletion cannot corrupt an in-flight response | `tests/browser_export_smoke.py`, `tests/test_file_response_leases.py`; **LULUS** in CI run #42405436400 |
| JOB-01 | Multi-file batch, progress and processing failure | Per-file progress and terminal done/failed state; previous image buffers released before next decode | `tests/test_processing_memory.py`, `tests/test_app.py`; **LULUS** in CI run #42405436400 |
| JOB-02 | Concurrent request over capacity and job cleanup | HTTP 429 when slots full; expired/orphaned files cleaned without deleting leased output | `tests/test_jobs.py`, `tests/test_job_cleanup_locks.py`; **LULUS** in CI run #42405436400 |
| RET-01 | Completed job and user opens results view | UI states 30-minute retention and container-recreation loss; cleanup respects active output leases | `tests/browser_export_smoke.py`, `tests/test_jobs.py`; UI warning **LULUS** in run #42406743222; cleanup lease regression **LULUS** in baseline run #42405436400 |
| BUILD-01 | Clean Docker build and app startup as non-root | Docker image builds; container serves UI and OpenAPI; no root runtime | `.github/workflows/tests.yml`; Docker build, non-root startup, browser/API smoke **LULUS** in run #42406743222 |
| RAW-01 | Pinned Nikon NEF ×2 and Canon 5D Mark IV CR2 fixtures with ExifTool | RAW decode finite sRGB; identity/creative LUT; TIFF/JPEG, ICC, orientation and camera metadata verified | `tests/test_raw_integration.py`; **LULUS** in CI run #42405436400 |
| PERF-01 | 2400×3200 float32 RGB synthetic image, 17³ LUT, 256-pixel tiles | Peak RSS < 6× source image byte size in fresh Linux subprocess | `tests/test_memory_footprint.py`; **LULUS** in CI run #42405436400 |
| PERF-02 | Three fresh-process runs on a representative real RAW from the target workstation; current measured sample is 4080×3072 (12.53 MP) DNG | For the measured workload: ≤120 s/image and ≤4 GiB peak RSS. Report median and maximum. A separate 24 MP / 8-core / 32-GB / NVMe stress profile remains a non-blocking capacity target, not a functional release requirement | User workstation: 3/3 runs passed; median 4.9646 s, max 5.0184 s; peak RSS max 473.35 MiB. **LULUS for 12.53 MP sample only**; no 24 MP extrapolation |
| VID-01 | Synthetic HLG BT.2020 10-bit source, NVIDIA NVDEC + libplacebo-managed Vulkan + NVENC | HLG output Main 10/BT.2020/HLG; Rec.709 output Main 10/BT.709; identity-LUT PSNR >30 dB | `tests/test_video_integration.py`; **LULUS on the user's RTX 3050 workstation** for synthetic source and identity LUT: 2 passed, 0 skipped; see `docs/ACCEPTANCE_EVIDENCE_LEDGER.md`. Arbitrary camera/container inputs and long-duration throughput are not certified. |
| DOC-01 | Clean checkout setup, feature limits, release notes, license and known limitations | Instructions reproduce the local Docker workflow; MIT license and hardware-dependent limitations are explicit | `README.md`, `CHANGELOG.md`, `LICENSE`; final doc review **BELUM DIJALANKAN** |

### Numerical quality and performance thresholds

- Float32 LUT identity: maximum absolute error **1e-6**.
- Analytic trilinear reference: maximum absolute error **2e-6**.
- Linear-light intensity blend: maximum absolute error **1e-6**; intensity endpoints exact array equality.
- TIFF: exact uint16 quantization equality to round-to-nearest.
- JPEG: lossy; validate RGB mode, ICC, dimensions and metadata, not exact pixel equality.
- Synthetic video identity-LUT round trip: PSNR **>30 dB** plus exact output codec/bit-depth/color metadata checks.
- Memory regression: peak RSS **<6×** the 2400×3200 float32 RGB input size on Linux.
- Measured workload target: **≤120 s per input RAW** and **≤4 GiB peak RSS** on the declared test workstation. The 12.53 MP DNG benchmark passed in three fresh processes (median 4.9646 s; max 5.0184 s; max RSS 473.35 MiB). The separate **24 MP / 8-core / 32-GB / NVMe** profile is retained as a non-blocking capacity/stress objective; no 24 MP performance claim is made.

## 5. Execution snapshot

GitHub Actions run **#42463321752** for PR #64 head commit `934ec567d68c99aff7d7193f1ab5845b29209e3a` completed successfully:
- Python/integration job: **122 passed, 2 skipped, 0 failed** in 80.38 seconds.
- Docker/UI/API/Playwright smoke job: **success**, including CPU and NVIDIA Compose validation, separate photo/video image builds, non-root container startup, and web UI/API schema smoke tests.
- The benchmark CLI import check from outside the repository root passed.
- The two skipped tests are the physical GPU video integration cases; the hosted runner does not provide the required libplacebo custom-LUT/GPU stack. The GPU path is separately recorded as locally tested on the user's RTX 3050 workstation, with its stated synthetic-input/identity-LUT limits.
- Run URL: https://github.com/bajomes/PhotoLUT/actions/runs/42463321752.

## 6. Candidate checkout and clean setup

The pull request candidate is published on `release/1.1.0-scope-and-acceptance`. From a fresh clone, use:

```bash
git clone https://github.com/bajomes/PhotoLUT.git
cd PhotoLUT
git fetch origin release/1.1.0-scope-and-acceptance
git switch --track origin/release/1.1.0-scope-and-acceptance
docker compose up --build -d
```

Open `http://127.0.0.1:8000`. This default path is the CPU photo workflow; NVIDIA passthrough is not required. To additionally exercise the optional HLG video workflow, use both Compose files:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build -d
```

The app's default work directory is container-local. Completed outputs are temporary; download them before the 30-minute retention window and before recreating the container. The optional video path requires the NVIDIA driver, NVIDIA Container Toolkit, Vulkan and a compatible FFmpeg build.

## 7. Environment, dependencies and reproducibility

- Runtime baseline: Python 3.12 in Docker `python:3.12-slim-trixie`; Docker Compose; Linux container. Browser smoke uses Playwright Chromium.
- Direct runtime dependencies are exactly pinned in `requirements.txt`; `requirements.lock` pins the resolved runtime graph and `requirements-dev.lock` pins the CI/development graph from the passing Python 3.12 Linux CI environment. These locks pin versions but do not yet record artifact hashes; cross-platform wheel resolution can still differ.
- System packages are installed from Debian Trixie plus Debian Sid for FFmpeg/libplacebo. The Sid repository is not pinned to a snapshot; exact system-package reproducibility is therefore not guaranteed.
- Photo processing is CPU-only. Video export requires a compatible NVIDIA GPU, driver, NVIDIA Container Toolkit, Vulkan and FFmpeg with the custom LUT option in libplacebo.
- CI covers real RAW fixtures and Docker/browser smoke, but hosted runners do not prove physical NVIDIA GPU execution.

## 8. Reference repositories and licensing

No third-party implementation has been copied or adapted for this scope baseline. No external reference repository has been used as a code source. Product comparisons above are workflow-level benchmarks only. Any future code adaptation must record the exact repository URL and commit/tag, license, attribution obligations, dependency impact and platform compatibility before code is adopted.

## 9. Release gate

The photo release is ready for user acceptance only when every **Required** functional criterion has executed successfully, no unresolved critical/high defect remains, a representative real-RAW workload has been measured against the per-image time/RSS limits, a clean Docker checkout builds and starts successfully, and the handover artifacts are present. A 24 MP stress profile is informative capacity evidence, not a prerequisite for functional correctness. Optional video GPU validation is reported separately and must not be described as passed when hardware was unavailable.

A green unit-test job, successful Docker build, UI screenshot, or code review alone is not sufficient evidence of release readiness.


## Evidence update — local full regression, 2026-11-08

The user synchronized candidate commit `94a98f9e4e0652ee30007ccdea99869157d05a34` and reported successful compilation plus **121 passed, 3 skipped, 0 failed in 9.68 seconds**. The three skips are the two Nikon NEF and one Canon CR2 RAW integration tests because the corresponding fixture files are absent from the local checkout; CI downloads these fixtures. The prior CI run `42460363433` was cancelled before pytest completed, so it is not counted as a CI pass. Its Docker job completed Compose validation, both image builds, non-root startup, and UI/API smoke steps before cancellation. The optional GPU video path remains separately verified on the user's NVIDIA RTX 3050 workstation as recorded in the evidence ledger.


## Performance criterion clarification — 2026-11-08

The original 24 MP / 8-core / 32-GB / NVMe profile was too specific to serve as a universal functional release gate: megapixel count is a workload dimension, not a correctness requirement. PERF-02 is therefore split into (a) measured performance on a representative real RAW from the target workstation, which is required and now passes for the supplied 12.53 MP DNG, and (b) the original 24 MP reference profile, retained as a non-blocking capacity objective. This change does not extrapolate the 12.53 MP measurements to 24 MP or claim performance on untested hardware.


## Local verification update — 2026-11-08

The user synchronized commit `934ec567d68c99aff7d7193f1ab5845b29209e3a` and ran the consolidated local verification command successfully:
- `.venv312/bin/python -m pip check`: no broken requirements.
- `compileall` over application, scripts and tests: passed.
- `pytest -q -rs`: **121 passed, 3 skipped, 0 failed** in 10.04 seconds.
- `scripts/benchmark_photo.py --help`: passed.
- `docker compose -f docker-compose.yml config --quiet`: passed.
- The three local skips are the two Nikon NEF and one Canon CR2 fixture tests; those RAW fixture files are absent from the local checkout. CI separately exercises downloaded fixtures.
- Working tree was clean after synchronization and verification. The local `.venv312/` and `photolut-diagnostic.txt` were preserved and added only to `.git/info/exclude`, not to the repository ignore rules.
