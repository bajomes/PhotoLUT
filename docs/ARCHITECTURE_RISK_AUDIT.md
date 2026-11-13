# PhotoLUT 1.1.0 Architecture and Risk Audit

**Audit basis:** source inspection of candidate branch `release/1.1.0-scope-and-acceptance`, currently at the commit recorded in the companion release/parity documents.  
**Scope:** source/configuration review, not a penetration test, independent clean-room build, or production deployment test.  
**Evidence labels:** **Observed** = directly visible in source/config; **Risk to test** = plausible consequence not yet demonstrated as a defect.

## 1. System architecture

- **Observed:** Python 3.12, FastAPI, vanilla HTML/CSS/JavaScript frontend, NumPy image transforms, rawpy/LibRaw RAW decoding, Pillow JPEG output, tifffile TIFF output, ExifTool metadata transfer, and Docker Compose.
- **Observed:** CPU photo processing and optional NVIDIA video processing are separate deployment paths. Default Compose binds the web port to `127.0.0.1:8000`; the GPU overlay requests all GPUs and sets NVIDIA driver capabilities.
- **Observed:** there is no database, durable queue, shared job store, or persistent project document in the reviewed photo job path.
- **Observed:** the default Docker work directory is `/var/lib/photolut/jobs` inside the container. Compose does not mount a named volume for it.

## 2. Photo pipeline

| Stage | Observed implementation | Contract / caveat |
|---|---|---|
| Upload | FastAPI multipart `UploadFile`; app reads in 1 MiB chunks into a per-job directory | RAW extensions allow-listed; per-RAW 200 MiB, LUT 10 MiB, batch total 512 MiB, max 20 RAW files. Multipart parsing/spooling occurs before route-level chunk limits; request-body/server limits should be independently configured for hostile network exposure. |
| Validation | Filename suffix allow-list, `.cube` suffix, sRGB-only colorspace, intensity range 0–1 | Suffix validation is not a full media signature/decoder validation. Decoder and LUT parser remain the semantic validation stage. |
| RAW decode | rawpy/LibRaw; camera white balance; output sRGB; 16-bit; no auto-bright; FBDD off; float32 normalized output | This is rendered sRGB, not scene-linear RAW development. Exact camera support depends on LibRaw and fixtures; current fixtures do not prove all models. |
| LUT | Parsed 3D `.cube`; trilinear interpolation; tile processing; non-finite results rejected; output clipped to [0,1] | LUT domain and interpolation behavior are covered by tests; out-of-gamut values are clipped. No configurable input/output transform graph or camera-log transform. |
| Intensity | Original and graded sRGB values converted to linear light, blended, re-encoded to sRGB; row-tiled temporaries | Exact 0/100% endpoints; 50% black/white browser fixture expects sRGB 188. This does not prove all pipeline preview/export equivalence. |
| Preview | Half-size RAW decode, max side 1440, 8-bit JPEG proxy with sRGB ICC; browser blends intensity | Preview is intentionally lower resolution and lossy; not pixel-identical to full-resolution export. |
| Export | JPEG quality 95, RGB; TIFF uint16 RGB; sRGB ICC embedded; ExifTool copies EXIF/XMP/IPTC and normalizes orientation/color-space tags | Metadata copy is best-effort; per-output boolean is surfaced. No claim of complete maker-note preservation. TIFF alpha is not part of the RGB contract. |
| Download | Manifest-addressed ZIP snapshot for JPEG/TIFF/all; atomic archive publish; output leases protect in-flight downloads | Individual output deletion serializes against archive generation and rejects active leases. |
| Cleanup | Completed jobs eligible after 1800 s; cleanup loop every 120 s; active leases protected; orphan directories cleaned | Retention is approximate: actual deletion can occur after the threshold at the next cleanup pass. |
| Restart | Job state is in memory; files are container-local by default | Restart/recreation loses in-memory job lookup and access to the container filesystem. No session recovery. |

## 3. Color and image-quality contract

1. Still photo processing enters the LUT stage as rendered, normalized sRGB RGB values. It is not a scene-linear, camera-native, wide-gamut, or HDR grading pipeline.
2. The RAW decode uses LibRaw camera white balance and sRGB output. Camera profile/demosaic options are not exposed as user controls in the reviewed workflow.
3. The 3D LUT is evaluated with trilinear interpolation over its declared parsed domain; non-finite arithmetic is rejected and output is clipped to normalized [0,1].
4. Intensity is blended in linear-light sRGB, then encoded back to sRGB. This is a documented semantic choice, not a claim that the creative LUT itself is a physically based transform.
5. JPEG and TIFF outputs carry an sRGB ICC profile. Metadata transfer is best-effort and normalizes orientation; metadata privacy/removal is not currently a user-selectable policy.
6. Preview uses a reduced-resolution decode and JPEG representation. Its slider blend semantics are tested, but preview/export numerical identity is not claimed.

## 4. Reliability, concurrency and state

- **Observed:** a process-local bounded semaphore defaults to one RAW job and accepts values 1 or 2. Jobs execute on daemon threads. The job registry, output locks, and leases are Python in-memory globals.
- **Risk to test / deployment constraint:** multiple Uvicorn/Gunicorn workers would each have independent job registries and semaphores. A request routed to a different worker may not find the job; concurrency limits would be per process, not global. The supported deployment should remain one application worker until shared state/queue coordination is implemented and tested.
- **Observed:** cleanup uses a daemon thread per application lifespan start; no durable scheduler is present.
- **Observed:** cancellation of the HTTP preview request waits for the worker thread to finish before temporary inputs and the processing slot are released. There is no batch cancel API; active LibRaw/export work is not cooperatively interruptible.
- **Observed:** a batch failure marks the job failed with an error message; already-created files may remain in the job directory until retention cleanup. The API does not present those partial outputs as a completed batch.
- **Risk to test:** worker/process crash while a job is running can leave orphaned files and no terminal job state. Orphan cleanup relies on directory age and only removes matching 32-character lowercase-hex job directories.
- **Observed:** output leases protect archive streaming and deletion/cleanup within a single process. They are not distributed leases.

## 5. Security and privacy review

This section records source-level observations; it does not assert an exploitable vulnerability.

| Area | Observed | Risk / required verification |
|---|---|---|
| Network exposure | Compose binds loopback by default | If users override port binding or deploy behind a public reverse proxy, no application authentication/authorization was observed on job/status/download/delete routes. Treat as a single-user trusted-local service unless protected externally. |
| Job isolation | Random UUID4 job IDs; route access is based on possession of the ID; no user/session ownership model observed | This is not per-user authorization. Test intended local threat model and ensure public deployment is not documented as safe without auth. |
| Uploads | Allow-listed extensions and explicit byte/count limits while copying to disk | Multipart parser has its own spooling behavior; enforce request body limits at ingress. Test malformed/truncated files and decompression/resource exhaustion. |
| Path handling | Input basename stripped; output stem allow-listed; ZIP/delete derive only basename and require resolved parent to equal output directory | Continue adversarial path tests; ensure every file-serving route validates job/output ownership and resolved paths. |
| Subprocess | ExifTool invocation uses argument array rather than shell command and has a 30 s timeout | Inspect video FFmpeg subprocess separately; test hostile filenames/metadata and timeout behavior. |
| Metadata privacy | EXIF/XMP/IPTC are copied best-effort | This can retain GPS/serial/owner metadata. Add a documented privacy policy and an explicit strip/preserve choice before any multi-user/cloud deployment. |
| Resource limits | App-level upload caps and bounded processing slots | CPU, memory, temporary-disk quota, HTTP request duration and rate limits are not a complete hostile-network defense. |
| Container | Runtime user is non-root; work directory owned by app user | Keep filesystem read-only where possible and add container resource limits in deployment guidance. |

## 6. Video deployment boundary

- The default Compose file does not request GPU devices; the GPU overlay adds `gpus: all`.
- The Dockerfile now has two explicit targets: `photo` (default Compose path) installs only LibRaw/ExifTool plus the pinned Python runtime; `video` extends `photo` with FFmpeg from Debian Sid and checks libplacebo, the custom .cube LUT option, NVENC, CUDA and Vulkan. The NVIDIA Compose overlay selects `target: video`; the default Compose file selects `target: photo`.
- The Python application still imports `video.py` and mounts its routes in both targets. The photo target therefore retains the API surface but has no FFmpeg executable; video inspection/processing must fail with a clear unavailable-runtime response. This behavior is a deliberate compatibility boundary and requires a runtime smoke test, not just an image build.
- The latest source candidate `d3ce6c81c28fc7e909515733cfc5cf28c7212aa2` passed hosted CI builds for both targets: the `photo` image was verified to omit FFmpeg and import the app; the `video` image passed libplacebo option checks, non-root startup, UI/API and browser smoke. This still does not prove actual NVDEC/Vulkan/libplacebo/NVENC execution on a compatible physical NVIDIA driver and GPU.
- Existing video processing is a single-source HLG/Rec.709 batch path. It is not a multitrack timeline editor and does not provide audio editing, clip transitions, keyframes, proxies or persistent editing projects.
- Until hardware-backed validation is recorded, describe video as experimental/hardware-gated or keep it outside the stable photo distribution.

## 7. Build and reproducibility findings

- **Observed:** Python lockfiles pin package versions but do not contain artifact hashes; installation is not enforced with `--require-hashes`.
- **Observed:** Docker base image uses the mutable tag `python:3.12-slim-trixie`, not a digest.
- **Observed:** the optional `video` Docker target adds Debian Sid without a snapshot timestamp. The selected FFmpeg/system package versions can change over time. The `photo` target no longer needs that Sid repository.
- **Observed:** GitHub Actions uses Ubuntu hosted runners and installs system tools from the current runner package repositories. The workflow pins GitHub Actions by commit SHA but not all OS packages.
- **Conclusion:** current CI demonstrates a successful functional build at a point in time, not hermetic or bit-for-bit reproducible builds.

## 8. Release-gate consequences

| ID | Criterion | Status | Evidence / blocker |
|---|---|---|---|
| ARC-01 | Photo pipeline and sRGB/LUT behavior documented | LULUS | Source inspection summarized above; numeric tests are separate evidence |
| ARC-02 | Single-worker deployment constraint explicitly enforced/documented | BELUM DIJALANKAN | In-memory state confirms constraint; deployment command/worker guard and multi-worker failure test not yet added |
| SEC-01 | Public multi-user authentication/isolation | TIDAK BERLAKU untuk default loopback-only single-user scope; TERHAMBAT untuk public deployment | No auth/ownership model observed; reverse proxy/network trust boundary must be explicit |
| SEC-02 | Upload limits, filename/path and subprocess protections | BELUM DIJALANKAN as a consolidated adversarial security suite | Existing focused validation tests exist; no full adversarial review executed |
| PRIV-01 | Metadata preservation/removal policy | BELUM DIJALANKAN | Current behavior copies descriptive EXIF/XMP/IPTC best-effort; GPS/serial privacy choice not configurable |
| JOB-01 | In-process progress, concurrency and cleanup | LULUS in hosted CI for covered single-process tests | Does not establish cross-worker coordination |
| JOB-02 | Multi-worker shared job state | TERHAMBAT / unsupported | Requires durable shared registry/queue or explicit one-worker enforcement |
| REPRO-01 | Python hash-verified dependency lock | GAGAL against requested reproducibility gate | Lockfiles contain versions only |
| REPRO-02 | Immutable Python base image and OS package snapshot | GAGAL against requested reproducibility gate | Mutable base tag and Debian Sid without snapshot |
| PERF-01 | Synthetic peak-memory regression | LULUS in prior recorded CI | Synthetic fixture only |
| PERF-02 | Three 24 MP reference-host runs | TERHAMBAT | Reference host and RAW fixture not available in this execution environment |
| VIS-01 | Calibrated display comparison | TERHAMBAT | Requires physical calibrated display and operator record |
| VID-01 | Physical NVIDIA pipeline validation | TERHAMBAT | Requires compatible GPU, driver, Vulkan and FFmpeg build |

## 9. Audit limitations

- No local checkout/working-tree inspection or local Docker build was possible through the available GitHub connector session. The two Docker build targets were separated in commit `0ee0d35...`; the corresponding hosted CI verification has since passed for both image targets in runs #42450261576 and #42450265261; physical GPU processing remains unverified.
- Hosted GitHub Actions results are inspected separately and cited by exact run/commit.
- No penetration test, multi-user deployment test, calibrated-display review, reference-host benchmark or physical GPU test was performed.
- Dependency license inventory has not yet been regenerated from the complete installed graph. The repository's MIT license was inspected; this is not a full third-party license compliance report.


## 10. Current candidate evidence (supersedes stale status snapshots above)

**Snapshot date:** 2026-11-13. **Current documentation branch head:** `d600fe604486878643f8219605be0dc02c008ad9`. The most recent tested application-code candidate is `934ec567d68c99aff7d7193f1ab5845b29209e3a`; the commits from that code candidate to the current head are documentation-only. This section corrects the historical gate statuses in sections 6, 8 and 9; it does not retroactively alter what was tested at earlier commits.

### Verified evidence

| Area | Current result | Scope of evidence |
|---|---|---|
| Hosted CI | **PASS**, run [#42463321752](https://github.com/bajomes/PhotoLUT/actions/runs/42463321752), code candidate `934ec56` | Python test job: 122 passed, 2 skipped. Docker smoke job passed, including separate photo/video builds, photo image without FFmpeg, non-root video container, and UI/API/browser smoke. |
| Local Python regression | **PASS**, on user's workstation at code candidate `934ec56` | `pytest -q -rs`: 121 passed, 3 skipped; `pip check`, `compileall`, benchmark CLI help, and Compose config validation passed. Three skips are RAW integration fixtures absent from that workstation. |
| NVIDIA video path | **PASS for the exercised synthetic path** | RTX 3050 Laptop GPU, driver 615.78.08, FFmpeg n9.0.2/libplacebo v7.360.1; targeted integration tests 2 passed. Synthetic HLG/Rec.2020 10-bit source with identity LUT completed Main10 HEVC output and expected BT.2020/HLG metadata. This is not broad footage, quality, or throughput certification. |
| Representative RAW performance | **PASS for the measured sample** | Three fresh-process runs on one 4080×3072 (12.53 MP) DNG: median 4.9646 s, slowest 5.0184 s, maximum peak RSS 473.35 MiB. No 24 MP performance extrapolation is claimed. |
| Repository synchronization | **PASS at snapshot** | User fast-forwarded to `d600fe6`; reported clean worktree. The three commits after `934ec56` changed documentation only. |

### Corrected release-gate status

| ID | Current status | Qualification |
|---|---|---|
| VID-01 | **LULUS, limited** | Physical GPU validation succeeded for the documented synthetic HLG/identity-LUT path on the RTX 3050 workstation. This supersedes the earlier “not performed” statement; it does not certify arbitrary inputs or sustained throughput. |
| PERF-02 | **LULUS, limited** | The agreed representative-workload gate is met for the single 12.53 MP DNG sample and three measured runs. The former 24 MP reference-host target remains a non-blocking capacity/stress objective; no 24 MP claim is made. |
| REPRO-01 | **GAGAL** | Python dependency lockfiles pin versions but do not provide hashes or enforce hash checking. |
| REPRO-02 | **GAGAL** | Docker base image remains tag-based and OS package sources are not snapshot-pinned. |
| VIS-01 | **BELUM DIJALANKAN** | Calibrated-display review still requires a physical calibrated display and operator evidence. |
| DOC-01 | **BELUM DIJALANKAN** | Complete direct/transitive third-party license inventory and review are not recorded. |
| ARC-02 / JOB-02 | **LULUS untuk single-host, single-worker guard / UNSUPPORTED untuk multi-worker atau multi-host** | Uvicorn Docker command menetapkan satu worker; ASGI lifespan memperoleh non-blocking OS file lock pada work directory dan menolak proses kedua. CI menguji contention/reacquisition dan Docker smoke lulus. Ini tidak menyediakan distributed coordination. |
| SEC-01 / PRIV-01 | **OUTSIDE DEFAULT LOCAL SCOPE / OPEN FOR PUBLIC DEPLOYMENT** | Default Compose is loopback-bound, but the application has no multi-user authentication/ownership model and no configurable metadata privacy policy. Do not expose publicly without an external authenticated boundary and an explicit metadata policy. |
| SEC-02 | **BELUM DIJALANKAN as a complete suite** | Existing focused validation tests and source controls are not a substitute for a consolidated adversarial security suite. |

### Corrected audit limitations

The earlier statement that no physical GPU test had been performed is superseded by the recorded local NVIDIA evidence above. The earlier 24 MP blocker is superseded by the accepted 12.53 MP representative-workload criterion; the 24 MP workload remains unmeasured and non-blocking. The hosted CI and local test evidence apply to code candidate `934ec56`, not to a claim that CI was rerun on documentation-only head `d600fe6`.

The following remain genuine release-hardening work, not documentation-only caveats: hash-enforced Python dependencies; immutable Docker base digest and OS package snapshots; a single-worker enforcement mechanism; complete dependency license inventory; calibrated visual review; and a consolidated adversarial security test pass. Public/multi-user deployment remains unsupported without authentication, ownership isolation, durable shared job state, and an explicit metadata privacy policy.


## 11. Single-worker guard implementation (2026-11-13)

The application now acquires a non-blocking OS file lock at `$PHOTOLUT_WORK_DIR/.photolut-worker.lock` during ASGI lifespan startup and holds the descriptor until shutdown. A second application process using the same work directory fails startup with an explicit error instead of silently creating a second in-memory job registry. The Docker image command also explicitly sets Uvicorn `--workers 1`. The lock file is intentionally retained; the kernel releases the advisory lock when the owning process exits, including an abnormal exit.

Implementation commits: `e01c21f` (application guard), `3c0d427` (contention/reacquisition test), and `ff61f8a` (Docker worker count). The test workflow triggered by `3c0d427` was pending at the time this audit entry was written. Therefore **ARC-02 is implemented but not yet verified by CI**; do not mark it LULUS until the new test and Docker startup smoke pass. This guard assumes the Linux/POSIX container runtime used by the supported Docker deployment; it does not provide distributed coordination across different hosts or separate, non-shared work directories.


### CI result for single-worker guard

Workflow run [#43405725804](https://github.com/bajomes/PhotoLUT/actions/runs/43405725804) completed successfully on 2026-11-13 for head `ea1315c03315169a5936c08b54ebd04163473db6`. Python job: **123 passed, 2 skipped, 0 failed** in 69.44 s. The two skips are the physical NVIDIA video integration tests; the hosted runner's CUDA initialization probe returned `Operation not permitted`, which is expected without an attached NVIDIA device. Docker smoke: **success**, including both image builds, photo-image FFmpeg exclusion/import, non-root video container, and UI/API browser smoke. This verifies the single-worker guard and container command on CI; physical GPU validation remains the separate RTX 3050 evidence above.
