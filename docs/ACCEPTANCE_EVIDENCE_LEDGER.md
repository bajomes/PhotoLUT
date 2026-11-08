# PhotoLUT 1.1.0 — Current Acceptance Evidence Ledger

**Candidate branch:** `release/1.1.0-scope-and-acceptance`  
**Source candidate commit:** `d3ce6c81c28fc7e909515733cfc5cf28c7212aa2`  
**Current CI evidence:** [PR #42450265261](https://github.com/bajomes/PhotoLUT/actions/runs/42450265261) and [push #42450261576](https://github.com/bajomes/PhotoLUT/actions/runs/42450261576)  
**Run environment:** GitHub-hosted Ubuntu 24.04 runner; Python 3.12.16; Docker Engine/Compose; Playwright Chromium.  
**Status vocabulary:** LULUS / GAGAL / BELUM DIJALANKAN / TERHAMBAT. A skipped hardware-dependent test is never counted as LULUS.

This ledger records the evidence available for the exact candidate commit above. It does not replace local acceptance on the declared target workstation or manual visual review.

## Execution summary

| Job | Result | Evidence |
|---|---|---|
| Python and integration | **LULUS** — 122 passed, 1 skipped, 0 failed; 79.30 s | CI run #42407685107, job `test`; log shows RAW fixture downloads/checksum, `compileall`, and `pytest -q -rs` |
| Docker/UI/API smoke | **LULUS** | CI run #42407685107, job `docker-smoke`; Compose validation, Docker build, unprivileged container, UI/API schema, JS syntax, Playwright browser export smoke |
| GPU video integration | **TERHAMBAT** | `tests/test_video_integration.py:79` skipped because hosted runner FFmpeg lacks libplacebo custom `.cube` LUT support |
| 24 MP reference performance | **TERHAMBAT** | No declared 8-core/32-GB/NVMe reference host available in this session |
| Calibrated-display visual review | **BELUM DIJALANKAN** | Requires target display, calibration state and human visual inspection |
| Dependency/system-image reproducibility audit | **BELUM DIJALANKAN** | Current locks pin Python versions but lack artifact hashes; base image is a mutable tag; Debian Sid packages are not snapshot-pinned |
| Full dependency license inventory | **BELUM DIJALANKAN** | Project MIT license inspected; complete direct/transitive dependency license report not produced |

## Acceptance records

The current automated test suite below ran on source candidate `d3ce6c81c28fc7e909515733cfc5cf28c7212aa2` in both push and pull-request workflows. The documentation-only follow-up commit does not change application source; CI evidence is tied to the source candidate SHA above.

| ID | Scenario and input | Environment | Expected result / predeclared tolerance | Actual result | Evidence / status |
|---|---|---|---|---|---|
| IMP-01 | Upload supported RAW fixture(s), valid `.cube`; reject invalid extensions, empty/malformed inputs and limits | Ubuntu 24.04, Python 3.12.16, real Nikon NEF ×2 and Canon CR2 fixture | Valid job accepted; invalid inputs rejected with actionable HTTP errors | Test suite passed | `tests/test_api_validation.py`, `tests/test_app.py`; **LULUS** |
| LUT-01 | Identity 3D LUT, including 2×2×2 fixture | Same CI Python environment | Maximum absolute float32 error ≤ 1e-6 | Test suite passed | `tests/test_core.py`; **LULUS** |
| LUT-02 | Analytic affine LUT and channel-order/interpolation fixtures | Same CI Python environment | Maximum absolute interpolation error ≤ 2e-6 | Test suite passed | `tests/test_core.py`; **LULUS** |
| LUT-03 | Malformed rows, invalid size/domain, NaN/Inf and overflow inputs | Same CI Python environment | Reject before producing a partial export | Test suite passed | `tests/test_core.py`, `tests/test_lut_overflow.py`; **LULUS** |
| INT-01 | LUT intensity 0%, 50%, 100% | Python tests and browser pixel fixture | Endpoints exact; linear-light sRGB midpoint error ≤ 1e-6; black/white 50% result encodes to sRGB 188 | Test suite and browser smoke passed | `tests/test_core.py`, `tests/browser_export_smoke.py`; **LULUS** |
| COL-01 | Values outside LUT domain and non-finite boundaries | Same CI Python environment | Domain handling deterministic; output finite and within [0,1] | Test suite passed | `tests/test_core.py`, `tests/test_memory_footprint.py`; **LULUS** |
| COL-02 | 16-bit TIFF from real RAW fixture | Same CI Python environment; Nikon/Canon fixtures | RGB uint16; round-to-nearest quantization; embedded sRGB ICC | Integration suite passed | `tests/test_raw_integration.py`; **LULUS** |
| COL-03 | JPEG from real RAW fixture | Same CI Python environment; Nikon/Canon fixtures | RGB JPEG quality 95; embedded sRGB ICC; dimensions and metadata checked, no lossless pixel-equality claim | Integration suite passed | `tests/test_raw_integration.py`; **LULUS** |
| COL-04 | Alpha-channel behavior | Scope contract; RGB RAW decode and RGB JPEG/TIFF outputs | Alpha is explicitly unsupported and not advertised | Excluded from release contract | `docs/RELEASE_SCOPE_AND_ACCEPTANCE.md`; **LULUS as scope exclusion**, not alpha preservation |
| PRE-01 | Preview and export use same LUT/domain/intensity semantics | Browser smoke; deterministic black/white pixels | Same transform semantics; no pixel identity claim because preview is reduced, 8-bit and JPEG encoded | Pixel assertions passed; calibrated display comparison not run | `tests/browser_export_smoke.py`; automated portion **LULUS**, calibrated visual portion **BELUM DIJALANKAN** |
| UI-01 | Export picker keyboard navigation, Tab/Shift+Tab wrap, Escape, backdrop and focus restoration | Docker container + Playwright Chromium | Dialog focus contained; close restores focus to trigger | Browser smoke passed | `tests/browser_export_smoke.py`; **LULUS** |
| UI-02 | JPEG, TIFF and all-format archive choices; delete a result during download lease | Python and Playwright tests | Correct archive contents; active download cannot be corrupted by deletion | Test suite and browser smoke passed | `tests/browser_export_smoke.py`, `tests/test_file_response_leases.py`; **LULUS** |
| JOB-01 | Multi-file batch progress and processing failure | Same CI Python environment | Visible per-file progress and terminal done/failed state; release large image buffers between files | Test suite passed | `tests/test_processing_memory.py`, `tests/test_app.py`; **LULUS** |
| JOB-02 | Concurrency limit and expired/orphan cleanup with active output lease | Same CI Python environment | Over-capacity returns HTTP 429; cleanup does not remove leased output | Test suite passed | `tests/test_jobs.py`, `tests/test_job_cleanup_locks.py`; **LULUS** |
| RET-01 | Completed result retention warning and cleanup behavior | Docker/Playwright and Python CI | Warn of 30-minute expiry and container-recreation loss; cleanup respects leases | UI warning in browser smoke; cleanup regression in Python suite | `tests/browser_export_smoke.py`, `tests/test_job_cleanup_locks.py`; **LULUS** |
| BUILD-01 | Clean Docker image build and startup as non-root (previous single-image architecture) | GitHub-hosted Ubuntu 24.04 Docker runner | Image builds; app serves UI/OpenAPI; runtime UID is non-zero | Previous image build, startup, non-root, UI/API smoke passed | `.github/workflows/tests.yml`, run #42407685107 job `docker-smoke`; **LULUS** for previous image architecture only |
| BUILD-02 | Build CPU photo target without FFmpeg and import the application | GitHub-hosted Ubuntu 24.04 Docker runner | `docker build --target photo`; image contains no `ffmpeg`; `import app` succeeds | Build and runtime assertion both completed successfully on source candidate SHA | Run #42450265261 job `docker-smoke`, step 5; **LULUS** |
| BUILD-03 | Build optional video target and smoke-test UI/API plus libplacebo custom LUT support | GitHub-hosted Ubuntu 24.04 Docker runner | `docker build --target video`; FFmpeg exposes libplacebo custom `.cube` LUT; non-root app serves UI/OpenAPI | Video image build, FFmpeg/libplacebo option checks, non-root startup, UI/API and browser export smoke all completed successfully. This does not execute GPU video processing on physical NVIDIA hardware. | Run #42450265261 job `docker-smoke`, steps 4 and 7–9; **LULUS** for image/build/smoke scope; VID-01 remains **TERHAMBAT** |
| RAW-01 | Decode two Nikon NEF and one Canon 5D Mark IV CR2; apply LUT and export | Python 3.12 CI; downloaded fixtures; Canon SHA-256 checked | Finite rendered sRGB; TIFF/JPEG, ICC, orientation and selected camera metadata validated | Integration suite passed | `tests/test_raw_integration.py`; **LULUS** for these three fixtures only |
| PERF-01 | Synthetic 2400×3200 float32 RGB image and 17³ LUT, tiled processing | Linux CI subprocess | Peak RSS < 6× source image byte size | Test suite passed | `tests/test_memory_footprint.py`; **LULUS** |
| PERF-02 | 24 MP RAW, single worker, reference 8 physical cores / 32 GB RAM / NVMe; three fresh-process runs | Target reference host unavailable | ≤120 s/photo and ≤4 GiB process peak RSS; report median and maximum | No valid reference-host measurements collected | `scripts/benchmark_photo.py`; **TERHAMBAT** |
| VID-01 | Synthetic HLG BT.2020 10-bit source through NVIDIA NVDEC, Vulkan/libplacebo and NVENC | Hosted CI runner has no required GPU FFmpeg custom-LUT option | HEVC Main 10; correct HLG/BT.2020 or SDR/BT.709 metadata; identity-LUT PSNR >30 dB | Skipped, not executed | `tests/test_video_integration.py:79`; **TERHAMBAT** |
| DOC-01 | Clean-checkout setup, feature limits, release notes, known limitations and license handoff | Repository docs review | Instructions match candidate; MIT notice and hardware limitations explicit | README, scope, architecture and parity docs exist; final handoff review still pending | `README.md`, `CHANGELOG.md`, `LICENSE`, `docs/`; **BELUM DIJALANKAN** for final review |

## Scope decisions

- **Wajib rilis:** RAW import and validation; 3D `.cube` import/application; 0–100% intensity; preview and before/after; reset/new batch; JPEG and 16-bit TIFF export; result removal; progress/actionable errors; retention warning.
- **Opsional / jalur validasi terpisah:** HLG/BT.2020 video inspection and GPU LUT export. This is an existing experimental batch workflow, not a promise of timeline editing or Gate A photo release readiness. Active-job cancellation is also optional because the current worker cannot safely interrupt a LibRaw decode/export mid-operation.
- **Di luar rilis 1.1.0:** undo/redo, persistent project recovery, exposure/contrast/WB/highlights/shadows/saturation/curves, crop/rotate editing, alpha workflow, camera-Log and HDR/wide-gamut still grading, video timeline/audio/general NLE functionality.
- Lightroom, Snapseed, DaVinci Resolve and Kdenlive are workflow-quality references only. The current release does not claim full-product parity.

## Current CI update — source candidate d3ce6c8

Both latest workflows for source candidate `d3ce6c81c28fc7e909515733cfc5cf28c7212aa2` completed successfully:

- PR run [#42450265261](https://github.com/bajomes/PhotoLUT/actions/runs/42450265261): Python/integration **122 passed, 1 skipped, 0 failed** in 57.67 s; Docker/UI/API job success.
- Push run [#42450261576](https://github.com/bajomes/PhotoLUT/actions/runs/42450261576): Python/integration **122 passed, 1 skipped, 0 failed** in 70.77 s; Docker/UI/API job success.
- Both Docker jobs validated CPU/NVIDIA Compose configurations, built `photo` and `video` targets, verified `photo` contains no FFmpeg and imports `app`, started the video-capable container as non-root, and passed UI/API plus Playwright browser export smoke.
- The skipped test is `tests/test_video_integration.py:79`, because the hosted runner lacks FFmpeg libplacebo custom `.cube` LUT support for the GPU integration. It is not a pass.

## Reproducibility and handoff limitations

The Python lockfiles pin versions but do not contain artifact hashes. The Docker base image tag is mutable, and FFmpeg is installed from Debian Sid without a repository snapshot. A successful Docker build therefore demonstrates a successful build at the time of the run, not a hermetic or bit-for-bit reproducible build. The project MIT license is present; a complete dependency/transitive-license inventory remains outstanding.

The application job registry and processing slots are process-local. The supported deployment remains a single application worker on loopback unless shared job state and public multi-user authentication/ownership controls are implemented and tested. Results are temporary and not recovered after container recreation.

## Release gate

**Gate A (PhotoLUT 1.1.0): NOT READY for user acceptance yet.** Core automated tests and both new Docker targets plus browser smoke pass on GitHub-hosted Ubuntu 24.04. The declared reference-host performance target, calibrated-display review, final documentation/license audit and reproducibility work are not closed.

**Gate B (comparator parity): NOT CONTRACTED.** No comparator versions/platforms/workflow subsets have been selected as mandatory parity requirements. The matrix in `FEATURE_PARITY_CONTRACT_DRAFT.md` remains a planning record, not evidence of parity.

No claim that all mandatory release criteria have passed is made by this ledger.
