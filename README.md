# PhotoLUT

PhotoLUT applies a 3D `.cube` creative LUT to RAW photographs and exports ready-to-use TIFF and JPEG files. It also includes an HDR video workflow for metadata inspection and HLG/BT.2020 LUT grading to HEVC Main 10 HDR MP4. Processing runs locally in the Docker container; media are not sent to a third-party image service.

## Quick start

Install Docker Desktop or Docker Engine with the Compose plugin. Check out the current project branch, then build and start PhotoLUT:

```bash
git fetch origin
git switch main
git pull --ff-only
docker compose up --build -d
```

Open http://127.0.0.1:8000 in a browser. The Compose port is bound to localhost by default. Job uploads and results stay in the container's temporary `/tmp/photolut-jobs` directory and are cleaned automatically after 30 minutes; Compose no longer creates a persistent `./jobs` mount on the host.

In the Video panel, choose an HLG source and inspect its metadata. The built-in Neutral HLG LUT is an identity transform; it preserves source colors without adding a creative tint. An optional custom HLG-domain `.cube` LUT can replace it. The video LUT export accepts confirmed HLG/BT.2020/10-bit sources only and verifies the encoded HDR result before returning it. After export, a synchronized before/after comparison lets you wipe between the original clip and the graded HDR result while previewing playback. The wipe is controlled directly inside the preview; playback includes a draggable seek timeline, 10-second skip controls, playback-speed selection, and fullscreen. Custom Rec.709 LUTs are not directly compatible with the current HLG-domain grading path. To stop the app:

```bash
docker compose down
```

## Current capabilities

- Recognized RAW extensions: CR2, CR3, NEF, ARW, SRF, SR2, DNG, ORF, RW2, RAF, PEF, and 3FR. Successful decoding depends on the exact camera model being supported by rawpy/LibRaw.
- 3D `.cube` LUTs, trilinear interpolation, and adjustable LUT intensity with a live preview of the first selected RAW photo.
- 16-bit TIFF and high-quality JPEG exports from the RAW batch workflow.
- Experimental Ultra HDR JPEG export from single-page 16-bit RGB/RGBA TIFF (8 MP limit); see [Ultra HDR photo export](docs/ultrahdr-photo-export.md).
- Before/after comparison slider, job progress, and ZIP download.
- sRGB ICC profile embedding and best-effort metadata copying with ExifTool.
- Original input filenames are retained for the result cards; output filenames are normalized for portable filesystem use.

## Video inspection (early foundation)

- Upload MP4, MOV, M4V, or MKV files up to 512 MiB to `POST /api/video/inspect`.
- FFprobe reports codec, dimensions, pixel format, estimated bit depth, frame rate, duration, color primaries, matrix, transfer function, range, and available Dolby Vision side-data/profile information.
- HLG (`arib-std-b67`) and PQ/HDR10 (`smpte2084`) are classified separately. The API reports whether BT.2020 primaries/matrix and at least 10-bit depth are confirmed, plus whether the source is at least 3840×2160 at approximately 30 fps. Inspection never upscales or changes frame rate.
- Video LUT processing uses FFmpeg `libplacebo` on the NVIDIA Vulkan device: decoded 10-bit frames are uploaded to the selected Vulkan device, the 3D `.cube` LUT is applied on the GPU, and the graded frames are downloaded for encoding. The current CUDA-to-Vulkan filter bridge uses explicit system-memory transfers, so this is GPU-accelerated but not a zero-copy pipeline. LUT intensity is baked into a temporary `.cube` using the HLG inverse/forward OETF so the GPU performs a single LUT lookup per pixel while preserving linear-light intensity blending. Encoding uses NVIDIA NVENC HEVC Main 10 (`hevc_nvenc`, preset P5, VBR constant-quality mode). There is no software encoder fallback: if NVDEC, a Vulkan/libplacebo custom-LUT path, or NVENC cannot be initialized, the export stops with FFmpeg diagnostics instead of silently switching to CPU processing. On hybrid laptops, the pipeline selects the Vulkan device by the `NVIDIA` vendor-name substring rather than relying on unstable device indices, preventing an integrated or software Vulkan device from being selected for LUT processing. GPU LUT acceleration requires FFmpeg with `libplacebo` custom `.cube` support, Vulkan 1.2, a compatible NVIDIA GPU/driver, NVIDIA Container Toolkit, and Docker GPU passthrough. The Docker image installs FFmpeg with the required `libplacebo` support.
- The `POST /api/video/process` workflow accepts confirmed HLG/BT.2020/10-bit footage and an HLG-domain `.cube` LUT, with adjustable intensity. The filter converts the BT.2020 YUV signal to HLG-encoded BT.2020 RGB, applies the LUT in its authored HLG signal domain, converts both the original and graded branches to linear-light RGB for intensity blending, then re-encodes HLG and converts back to limited-range BT.2020 HLG YUV. Linear-light blending avoids mixing nonlinear HLG code values directly. Output is encoded as HEVC Main 10 (`yuv420p10le`) with HLG/BT.2020 VUI tags and is re-probed before delivery; the API rejects any result that does not verify as 10-bit HLG/BT.2020. Dolby Vision sources are rejected because re-encoding would discard dynamic metadata. HDR10/PQ is inspected, but LUT grading in this release is HLG-only. The included Neutral HLG LUT is an identity transform for HLG-encoded BT.2020 RGB. It does not add a creative look or change the source color values; use a compatible HLG/BT.2020 LUT for creative grading. It is not an SDR LUT and must not be used on Rec.709 or camera-Log footage. Processing is limited to one video at a time, 512 MiB input, 10 MiB LUT, and a 20-minute FFmpeg timeout. Do not interpret a missing color tag as proof that footage is SDR.

## TikTok delivery considerations

TikTok's current [Content Posting API media guide](https://developers.tiktok.com/doc/content-posting-api-media-transfer-guide) lists MP4/MOV/WebM containers, H.264 (recommended) and H.265 codecs, 23–60 fps, dimensions up to 4096 pixels per side, and a 4 GB upload limit. Its published upload specification does not define an HDR transfer function, color primaries/matrix, bit-depth requirement, or Dolby Vision profile. Therefore, PhotoLUT cannot promise that TikTok will retain HDR or Dolby Vision metadata or deliver HDR playback after its server-side processing.

PhotoLUT's HLG LUT export produces an HEVC Main 10 HLG/BT.2020 master. TikTok's published upload specification does not promise HDR preservation, so the app cannot guarantee that a posted video will remain HDR after platform processing. Keep the verified PhotoLUT HDR master as the archival source and confirm playback on the target account and devices after upload. Do not treat a 4K source or a larger bitrate as a guarantee of 4K HDR playback.

## Verification coverage

GitHub Actions tests real RAW decoding and exports with two Nikon NEF samples and one Canon CR2 sample. The integration checks cover identity and creative LUTs, 16-bit TIFF pixels, JPEG output, embedded sRGB profiles, orientation, and selected camera metadata. The CI suite does not verify every listed extension or every camera model; validate samples from each target camera before relying on it for production work. A synthetic HLG video integration test is enabled only on runners that expose NVENC and FFmpeg `libplacebo` custom `.cube` LUT support; it converts a BT.709 test pattern into 10-bit BT.2020/HLG, runs the real FFmpeg GPU LUT export, and verifies the resulting HEVC Main 10/HLG/BT.2020 metadata and AAC audio. Standard hosted CI runners without that GPU stack skip this hardware-dependent integration test; passing their unit tests and Docker smoke test does not prove execution on a physical NVIDIA GPU. The test suite also checks that the built-in HLG LUT is a valid 3D cube. A separate CI job builds the Docker image and smoke-tests the web UI and OpenAPI schema.

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

Use Python 3.12 for local development:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pytest
pytest -q
```

On Windows PowerShell, activate the environment with `.venv\Scripts\Activate.ps1`.

Automated tests cover LUT parsing, interpolation, malformed LUT rejection, upload validation and limits, API processing and export, output profiles, metadata behavior, and job cleanup. Real-RAW CI fixtures currently cover Nikon NEF and Canon CR2; other camera models still need representative validation.


## License

PhotoLUT is distributed under the MIT License. See [LICENSE](LICENSE).
