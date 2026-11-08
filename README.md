# PhotoLUT

PhotoLUT applies a 3D `.cube` creative LUT to RAW photographs and exports ready-to-use TIFF and JPEG files. It also includes an HLG/BT.2020 video workflow that can export either HDR HLG/BT.2020 or tone-mapped SDR/BT.709 HEVC Main 10, depending on the selected LUT profile. Processing runs locally in the Docker container; media are not sent to a third-party image service.

## Quick start

Install Docker Desktop or Docker Engine with the Compose plugin. Check out the current project branch, then build and start PhotoLUT for the CPU-based RAW photo workflow:

```bash
git fetch origin
git switch main
git pull --ff-only
docker compose up --build -d
```

Open http://127.0.0.1:8000 in a browser. The default Compose configuration does not require an NVIDIA GPU, because RAW photo processing runs on the CPU. Job uploads and results stay inside the container at `/var/lib/photolut/jobs` and become eligible for cleanup after 30 minutes (the cleanup task runs every 2 minutes); Compose does not mount that directory onto the host. Results are not restored after container recreation.

To enable the separate HLG video workflow, install a compatible NVIDIA driver and NVIDIA Container Toolkit, then start with the optional GPU overlay. The overlay selects the `video` Docker build target, which layers FFmpeg/libplacebo and Vulkan support on top of the common photo runtime:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build -d
```

The default `photo` build target intentionally excludes FFmpeg and Vulkan packages. The optional `video` target adds the Debian Sid FFmpeg build and verifies libplacebo custom `.cube` LUT support, NVENC, CUDA and Vulkan at image-build time. Both targets share the same Python application and runtime lockfile. Video API routes remain visible in the CPU image but report that FFmpeg is unavailable when invoked; use the GPU overlay for video processing. When stopping a GPU-enabled instance, use the same two Compose files with `down`.

In the Video panel, inspect an HLG/BT.2020 source and select the color space in which the uploaded creative LUT was authored. The built-in Neutral HLG LUT is an identity transform; it preserves source colors without adding a creative tint. Choose **HLG / BT.2020** for a LUT authored for HLG-encoded BT.2020 RGB; the export remains HDR HLG. Choose **Rec.709** for standard SDR creative LUTs such as Sedona Standard; PhotoLUT tone-maps the HLG source to SDR BT.709 on the NVIDIA GPU before applying the LUT, and the export is correctly tagged SDR BT.709 rather than being mislabeled as HDR. Camera-Log LUTs are not supported. Both paths encode HEVC Main 10 and verify their output color metadata before returning the file. After export, a synchronized before/after comparison lets you wipe between the original clip and the graded result while previewing playback. The wipe is controlled directly inside the preview; playback includes a draggable seek timeline, 10-second skip controls, playback-speed selection, and fullscreen. To stop the app:

```bash
docker compose down
```

## Current capabilities

- Recognized RAW extensions: CR2, CR3, NEF, ARW, SRF, SR2, DNG, ORF, RW2, RAF, PEF, and 3FR. Successful decoding depends on the exact camera model being supported by rawpy/LibRaw.
- 3D `.cube` LUTs, trilinear interpolation, and adjustable LUT intensity blended in linear-light sRGB, with a live preview of the first selected RAW photo.
- 16-bit TIFF and high-quality JPEG exports.
- Before/after comparison slider, job progress, and ZIP download.
- sRGB ICC profile embedding and best-effort metadata copying with ExifTool.
- Original input filenames are retained for the result cards; output filenames are normalized for portable filesystem use.

## Photo processing and GPU requirements

The RAW-photo workflow currently uses rawpy/LibRaw for demosaicing and NumPy for tiled 3D LUT interpolation. These photo stages run on the CPU; Docker GPU passthrough does not automatically accelerate them. The NVIDIA GPU path described below applies to HLG video processing only. The application limits RAW processing to one heavy job by default and processes LUT interpolation in bounded tiles to reduce temporary memory, but CPU temperature and processing time still depend on the camera RAW dimensions, CPU cooling, and LibRaw workload. Do not interpret successful Docker startup or CPU-only CI as proof of photo GPU acceleration. GPU acceleration for RAW demosaicing must be implemented against a backend that explicitly supports the target GPU and verified on the actual NVIDIA hardware before it can be advertised as available.

## Video inspection (early foundation)

- Upload MP4, MOV, M4V, or MKV files up to 512 MiB to `POST /api/video/inspect`.
- FFprobe reports codec, dimensions, pixel format, estimated bit depth, frame rate, duration, color primaries, matrix, transfer function, range, and available Dolby Vision side-data/profile information.
- HLG (`arib-std-b67`) and PQ/HDR10 (`smpte2084`) are classified separately. The API reports whether BT.2020 primaries/matrix and at least 10-bit depth are confirmed, plus whether the source meets the 4K30-or-higher threshold (at least 3840×2160 and approximately 30 fps or higher). Inspection never upscales or changes frame rate.
- Video LUT processing uses FFmpeg `libplacebo` with its internally managed Vulkan context. NVDEC decodes 10-bit frames on the NVIDIA GPU; the filter graph downloads decoded frames to system-memory P010 before passing them to libplacebo, which manages its own Vulkan upload/download internally. This is a GPU-processing path with explicit CUDA-to-system-memory transfer, not a zero-copy pipeline. An externally initialized FFmpeg Vulkan device is deliberately not injected: on the validated hybrid NVIDIA laptop, doing so caused libplacebo filter-graph initialization to fail, while libplacebo's internally managed context succeeded. LUT intensity is baked into a temporary `.cube` in the selected LUT's linear-light domain (HLG or BT.1886) so the GPU performs a single LUT lookup per pixel while preserving linear-light intensity blending. Encoding uses NVIDIA NVENC HEVC Main 10 (`hevc_nvenc`, preset P5, VBR constant-quality mode). There is no software encoder fallback: if NVDEC, libplacebo's Vulkan path, or NVENC cannot be initialized, the export stops with FFmpeg diagnostics instead of silently switching to CPU processing. GPU LUT processing requires the optional `video` image target with FFmpeg `libplacebo` custom `.cube` support, a compatible NVIDIA GPU/driver, NVIDIA Container Toolkit, Vulkan support and Docker GPU passthrough. The default `photo` image does not install FFmpeg or Vulkan packages.
- The `POST /api/video/process` workflow accepts confirmed HLG/BT.2020/10-bit footage, a `.cube` LUT, an intensity value, and a declared LUT profile. For **HLG / BT.2020**, the filter applies the LUT in its authored HLG signal domain, blends intensity in HLG linear light, and exports verified HEVC Main 10 HLG/BT.2020. For **Rec.709**, libplacebo first tone-maps HLG to SDR BT.709 with the BT.2390 operator, then applies the creative LUT in native Rec.709 RGB and exports verified 10-bit HEVC SDR/BT.709. The Rec.709 path is deliberately an SDR delivery path; it does not label tone-mapped SDR pixels as HDR. Rec.709 intensity is blended in BT.1886 linear light. Both modes use NVDEC, libplacebo's internally managed Vulkan context and NVENC only; there is no software video-processing fallback. The included Neutral HLG LUT is an identity transform for HLG-encoded BT.2020 RGB. Standard creative LUTs such as Sedona Standard should use the Rec.709 profile, while LUTs explicitly authored for HLG/BT.2020 should use the HLG profile. Camera-Log LUTs are not supported. Dolby Vision sources are rejected because re-encoding would discard dynamic metadata. HDR10/PQ is inspected, but LUT grading in this release accepts HLG input only. Processing is limited to one video at a time, 512 MiB input, 10 MiB LUT, and a 20-minute FFmpeg timeout. Do not interpret a missing color tag as proof that footage is SDR.

## TikTok delivery considerations

TikTok's current [Content Posting API media guide](https://developers.tiktok.com/doc/content-posting-api-media-transfer-guide) lists MP4/MOV/WebM containers, H.264 (recommended) and H.265 codecs, 23–60 fps, dimensions up to 4096 pixels per side, and a 4 GB upload limit. Its published upload specification does not define an HDR transfer function, color primaries/matrix, bit-depth requirement, or Dolby Vision profile. Therefore, PhotoLUT cannot promise that TikTok will retain HDR or Dolby Vision metadata or deliver HDR playback after its server-side processing.

PhotoLUT's HLG LUT export produces an HEVC Main 10 HLG/BT.2020 master. TikTok's published upload specification does not promise HDR preservation, so the app cannot guarantee that a posted video will remain HDR after platform processing. Keep the verified PhotoLUT HDR master as the archival source and confirm playback on the target account and devices after upload. Do not treat a 4K source or a larger bitrate as a guarantee of 4K HDR playback.

## Verification coverage

GitHub Actions tests real RAW decoding and exports with two Nikon NEF samples and one Canon CR2 sample. The integration checks cover identity and creative LUTs, 16-bit TIFF pixels, JPEG output, embedded sRGB profiles, orientation, and selected camera metadata. The CI suite does not verify every listed extension or every camera model; validate samples from each target camera before relying on it for production work. A synthetic HLG video integration test is enabled only on runners that expose NVENC and FFmpeg `libplacebo` custom `.cube` LUT support; it converts a BT.709 test pattern into 10-bit BT.2020/HLG, runs both real NVIDIA GPU export profiles (HLG HDR and tone-mapped Rec.709 SDR), and verifies HEVC Main 10 plus the correct color metadata for each output. Standard hosted CI runners without that GPU stack skip this hardware-dependent integration test; passing their unit tests and Docker smoke test does not prove execution on a physical NVIDIA GPU. The test suite also checks that the built-in HLG LUT is a valid 3D cube. A separate CI job builds both Docker targets. It verifies that the `photo` target imports the application without FFmpeg, and smoke-tests the UI/API using the `video` target with its required FFmpeg filters.

When running `pytest -q` locally without sample files in `test-data/`, the real-RAW integration cases are skipped. Set `PHOTOLUT_TEST_RAW_DIR` to a directory containing the three fixture files to run them locally.

## Input color space

The current RAW pipeline produces sRGB-encoded RGB data using the camera's recorded white balance and disables automatic brightness amplification for more predictable batch behavior. Select a LUT whose expected input is compatible with sRGB-encoded display-referred RGB.

Camera Log workflows (such as S-Log, V-Log, or C-Log) are **not supported yet**. Correct support requires an explicit transfer-function and gamut transform for the specific camera profile and the LUT's output encoding. A generic power function is not a valid substitute for a camera Log transform.

## Upload and processing limits

- Up to 20 RAW photos per batch.
- Maximum 200 MiB per RAW file.
- Maximum 10 MiB per `.cube` LUT.
- Maximum 512 MiB total upload size per batch.
- One processing job at a time by default. Set `PHOTOLUT_CONCURRENCY=2` in the shell before `docker compose up` to allow two jobs; only values `1` and `2` are accepted. Additional requests receive HTTP 429 while all slots are occupied.
- LUT size must be between 2 and 128 entries per dimension.

These limits help keep local CPU, memory, and disk usage bounded. LUT interpolation and output quantization run in tiles/row chunks to limit temporary allocations, but decoded and graded full-resolution images must still reside in memory. Very high-resolution RAW files can therefore require substantial RAM during demosaicing and export.

## Metadata

ExifTool is installed in the Docker image. PhotoLUT attempts to copy camera metadata to both exports. A warning appears when metadata copying fails; review the output metadata when preservation is important. The exported pixels are rendered images, not RAW files, and some camera-specific metadata cannot sensibly be preserved in a processed image.

## Development and tests

Use Python 3.12 to match the CI environment. Create an isolated virtual environment and install the development lockfile (which includes pytest):

```bash
python3.12 --version
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.lock
python -m pip check
python -m compileall -q app.py core.py jobs.py video.py scripts tests
python -m pytest -q -rs
```

Use `python -m pytest` rather than relying on a standalone `pytest` executable being present on `PATH`. If Python 3.12 is not installed, install it before creating the environment; the CI baseline is Python 3.12, not the host's default Python version. On Windows PowerShell, use the Python 3.12 launcher to create the environment (for example, `py -3.12 -m venv .venv`) and activate it with `.venv\\Scripts\\Activate.ps1`.

Automated tests cover LUT parsing, interpolation, malformed LUT rejection, upload validation and limits, API processing and export, output profiles, metadata behavior, and job cleanup. Real-RAW CI fixtures currently cover Nikon NEF and Canon CR2; other camera models still need representative validation. The three RAW integration fixtures must be downloaded separately to run those cases locally; without them, the integration tests are skipped.

## Release engineering records

- [PhotoLUT 1.1.0 release scope and acceptance matrix](docs/RELEASE_SCOPE_AND_ACCEPTANCE.md)
- [Current acceptance evidence ledger](docs/ACCEPTANCE_EVIDENCE_LEDGER.md)
- [CI verification addendum (2026-11-08)](docs/CI_VERIFICATION_2026-11-08.md)
- [Architecture and risk audit](docs/ARCHITECTURE_RISK_AUDIT.md)
- [Feature-parity contract draft (Gate B; product decision pending)](docs/FEATURE_PARITY_CONTRACT_DRAFT.md)

The parity draft is not a claim of feature parity. Gate A release closure and Gate B parity are assessed independently.

## License

PhotoLUT is distributed under the MIT License. See [LICENSE](LICENSE).
