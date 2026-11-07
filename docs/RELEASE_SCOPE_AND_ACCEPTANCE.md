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
| IMP-01 | Upload 1–20 RAW files, valid `.cube`, supported sRGB setting | Valid job created; invalid extension, empty/malformed upload and size/count limit rejected with actionable HTTP error | `tests/test_api_validation.py`, `tests/test_app.py`; **BELUM DIJALANKAN** on release baseline |
| LUT-01 | Identity 2×2×2 and larger LUTs | Identity error max absolute ≤ 1e-6 in float32 synthetic test | `tests/test_core.py`; **BELUM DIJALANKAN** on release baseline |
| LUT-02 | Channel permutation and analytic affine LUT | Trilinear result max absolute ≤ 2e-6 for supported synthetic fixture | `tests/test_core.py`; **BELUM DIJALANKAN** on release baseline |
| LUT-03 | Malformed rows, duplicate/missing size, invalid domain, NaN/Inf, over-limit LUT | Reject before export; no partial success artifact | `tests/test_core.py`, `tests/test_lut_overflow.py`; **BELUM DIJALANKAN** on release baseline |
| INT-01 | Intensity 0, 0.5, 1 | 0 and 1 endpoints array-equal to original/graded; 0.5 blend in linear-light sRGB with max absolute error ≤ 1e-6 against reference | `tests/test_core.py`; **BELUM DIJALANKAN** on release baseline |
| COL-01 | LUT domain clipping and finite image boundaries | Values are clipped to declared LUT domain, output RGB remains finite and in [0,1] | `tests/test_core.py`, `tests/test_memory_footprint.py`; **BELUM DIJALANKAN** on release baseline |
| COL-02 | TIFF export from deterministic RGB float fixture | uint16 RGB samples exactly equal `rint(pixel × 65535)`; embedded sRGB ICC present | `tests/test_raw_integration.py`; **BELUM DIJALANKAN** on release baseline |
| COL-03 | JPEG export from deterministic RGB fixture | RGB mode, quality 95, embedded sRGB ICC; lossy pixel equality is not asserted | `tests/test_raw_integration.py`; **BELUM DIJALANKAN** on release baseline |
| COL-04 | RAW alpha / TIFF alpha input | Not applicable; RGB-only input/output contract. No alpha preservation claim | Scope contract; **LULUS** as an explicit exclusion |
| PRE-01 | Preview and final export of same RAW/LUT | Same LUT/domain/intensity semantics; no pixel-identical requirement because preview uses half-size decode, 8-bit quantization and JPEG proxy. Compare UI preview against export visually on calibrated display as a separate manual check | `app.py` preview path; manual check **BELUM DIJALANKAN** |
| UI-01 | Open format picker, Tab/Shift+Tab, wrap, Escape, close, backdrop, keyboard focus recovery | Focus remains in dialog; choices are traversed before close control; focus returns to trigger on close | `tests/browser_export_smoke.py`; latest CI for fix commit pending |
| UI-02 | Select JPEG, TIFF, all; remove result; download during remove | Correct archive content; deletion cannot corrupt an in-flight response | `tests/browser_export_smoke.py`, `tests/test_file_response_leases.py`; **BELUM DIJALANKAN** on release baseline |
| JOB-01 | Multi-file batch, progress and processing failure | Per-file progress and terminal done/failed state; previous image buffers released before next decode | `tests/test_processing_memory.py`, `tests/test_app.py`; **BELUM DIJALANKAN** on release baseline |
| JOB-02 | Concurrent request over capacity and job cleanup | HTTP 429 when slots full; expired/orphaned files cleaned without deleting leased output | `tests/test_jobs.py`, `tests/test_job_cleanup_locks.py`; **BELUM DIJALANKAN** on release baseline |
| BUILD-01 | Clean Docker build and app startup as non-root | Docker image builds; container serves UI and OpenAPI; no root runtime | `.github/workflows/tests.yml`; latest fix commit CI pending |
| RAW-01 | Pinned Nikon NEF ×2 and Canon 5D Mark IV CR2 fixtures with ExifTool | RAW decode finite sRGB; identity/creative LUT; TIFF/JPEG, ICC, orientation and camera metadata verified | `tests/test_raw_integration.py`; latest pre-fix commit test job passed |
| PERF-01 | 2400×3200 float32 RGB synthetic image, 17³ LUT, 256-pixel tiles | Peak RSS < 6× source image byte size in fresh Linux subprocess | `tests/test_memory_footprint.py`; latest pre-fix commit test job passed |
| PERF-02 | 24 MP RAW, reference CPU 8 physical cores / 32 GB RAM / NVMe SSD, single job | Target: ≤120 s per image; process peak RSS ≤4 GiB. Measure wall time and process peak RSS from fresh process, 3 runs, report median and max. Not yet measured on reference hardware | Benchmark not yet implemented/executed; **TERHAMBAT** by absence of reference host |
| VID-01 | Synthetic HLG BT.2020 10-bit source, NVIDIA NVDEC + Vulkan/libplacebo + NVENC | HLG output Main 10/BT.2020/HLG; Rec.709 output Main 10/BT.709; identity-LUT PSNR >30 dB | `tests/test_video_integration.py`; **TERHAMBAT** without supported NVIDIA hardware/driver/container runtime |
| DOC-01 | Clean checkout setup, feature limits, release notes, license and known limitations | Instructions reproduce the local Docker workflow; MIT license and hardware-dependent limitations are explicit | `README.md`, `CHANGELOG.md`, `LICENSE`; final doc review **BELUM DIJALANKAN** |

### Numerical quality and performance thresholds

- Float32 LUT identity: maximum absolute error **1e-6**.
- Analytic trilinear reference: maximum absolute error **2e-6**.
- Linear-light intensity blend: maximum absolute error **1e-6**; intensity endpoints exact array equality.
- TIFF: exact uint16 quantization equality to round-to-nearest.
- JPEG: lossy; validate RGB mode, ICC, dimensions and metadata, not exact pixel equality.
- Synthetic video identity-LUT round trip: PSNR **>30 dB** plus exact output codec/bit-depth/color metadata checks.
- Memory regression: peak RSS **<6×** the 2400×3200 float32 RGB input size on Linux.
- Reference performance target: **≤120 s / 24 MP RAW** and **≤4 GiB peak RSS**, single worker, on the hardware definition in PERF-02. This target is predeclared, not yet measured or passed.

## 5. Environment, dependencies and reproducibility

- Runtime baseline: Python 3.12 in Docker `python:3.12-slim-trixie`; Docker Compose; Linux container. Browser smoke uses Playwright Chromium.
- Python runtime dependencies are version-constrained in `requirements.txt`; no pip lockfile is present. CI installs from that manifest, so fully hash-locked reproducibility is not yet established.
- System packages are installed from Debian Trixie plus Debian Sid for FFmpeg/libplacebo. The Sid repository is not pinned to a snapshot; exact system-package reproducibility is therefore not guaranteed.
- Photo processing is CPU-only. Video export requires a compatible NVIDIA GPU, driver, NVIDIA Container Toolkit, Vulkan and FFmpeg with the custom LUT option in libplacebo.
- CI covers real RAW fixtures and Docker/browser smoke, but hosted runners do not prove physical NVIDIA GPU execution.

## 6. Reference repositories and licensing

No third-party implementation has been copied or adapted for this scope baseline. No external reference repository has been used as a code source. Product comparisons above are workflow-level benchmarks only. Any future code adaptation must record the exact repository URL and commit/tag, license, attribution obligations, dependency impact and platform compatibility before code is adopted.

## 7. Release gate

The photo release is ready for user acceptance only when every **Required** criterion has executed successfully, no unresolved critical/high defect remains, the reference performance target is measured, a clean Docker checkout is reproducible, and the handover artifacts are present. Optional video GPU validation is reported separately and must not be described as passed when hardware was unavailable.

A green unit-test job, successful Docker build, UI screenshot, or code review alone is not sufficient evidence of release readiness.
