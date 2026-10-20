# PhotoLUT

PhotoLUT applies a 3D `.cube` creative LUT to RAW photographs and exports ready-to-use TIFF and JPEG files. Processing runs locally in the Docker container; photos are not sent to a third-party image service.

## Quick start

Install Docker Desktop or Docker Engine with the Compose plugin, then run:

```bash
docker compose up --build -d
```

Open http://127.0.0.1:8000 in a browser. The Compose port is bound to localhost by default. To stop the app:

```bash
docker compose down
```

## Current capabilities

- Batch processing of supported RAW formats: CR2, CR3, NEF, ARW, SRF, SR2, DNG, ORF, RW2, RAF, PEF, and 3FR.
- 3D `.cube` LUTs, trilinear interpolation, and adjustable LUT intensity.
- 16-bit TIFF and high-quality JPEG exports.
- Before/after comparison slider, job progress, and ZIP download.
- sRGB ICC profile embedding and best-effort metadata copying with ExifTool.
- Original input filenames are retained for the result cards; output filenames are normalized for portable filesystem use.

## Input color space

The current RAW pipeline produces sRGB-encoded RGB data using the camera's recorded white balance and disables automatic brightness amplification for more predictable batch behavior. Select a LUT whose expected input is compatible with sRGB-encoded display-referred RGB.

Camera Log workflows (such as S-Log, V-Log, or C-Log) are **not supported yet**. Correct support requires an explicit transfer-function and gamut transform for the specific camera profile and the LUT's output encoding. A generic power function is not a valid substitute for a camera Log transform.

## Upload and processing limits

- Up to 20 RAW photos per batch.
- Maximum 200 MiB per RAW file.
- Maximum 10 MiB per `.cube` LUT.
- Maximum 512 MiB total upload size per batch.
- Up to two processing jobs at a time; additional requests receive HTTP 429 while the processor is busy.
- LUT size must be between 2 and 128 entries per dimension.

These limits help keep local CPU, memory, and disk usage bounded. Very high-resolution RAW files can still require substantial memory during demosaicing.

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

Automated tests cover LUT parsing, identity and channel-order behavior, interpolation, invalid LUT data, intensity blending, output profiles, and job-cleanup behavior. RAW-file integration tests should also be run with sample files from each supported camera family before a release.
