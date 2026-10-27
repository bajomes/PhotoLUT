# Changelog

Notable changes to PhotoLUT are documented here.

## Unreleased

### Maintenance
- Refresh Python dependency constraints for multipart uploads, NumPy, Pillow, Uvicorn, and tifffile; verify the combined set in CI.

### Fixed
- Bound peak memory during 3D LUT application by processing tiles without changing the established per-pixel arithmetic.
- Quantize TIFF and JPEG output buffers in row chunks to reduce large temporary allocations during export.
- Default RAW processing concurrency to one job, with a validated optional setting for two concurrent jobs.
- Add bit-exact LUT regression checks and a Linux subprocess peak-RSS test.

## 1.0.0 — 2026-10-25

### Added
- Batch processing of RAW photographs using 3D `.cube` creative LUTs.
- Adjustable LUT intensity and before/after comparison previews.
- 16-bit TIFF and high-quality JPEG exports, plus ZIP download for batch results.
- Embedded sRGB ICC profiles and best-effort transfer of descriptive camera metadata.
- Local Docker Compose quick start and automatic cleanup of expired and orphaned job files.
- Automated tests for LUT parsing and interpolation, API validation, job cleanup, and output exports.
- Real-RAW integration coverage for two Nikon NEF samples and a Canon CR2 sample.

### Reliability and safety
- Validation for malformed LUTs, supported filename extensions, upload sizes, and concurrent processing capacity.
- Safer output filenames and guarded result-file paths.
- Color-space and orientation metadata are explicitly normalized for rendered exports.
- GitHub Actions dependencies are pinned to official immutable action commits and checked by Dependabot.
- CI builds the Docker image and smoke-tests the running app and its OpenAPI schema.

### Known limitations
- Camera Log workflows such as S-Log, V-Log, and C-Log are not supported.
- RAW decoding depends on rawpy/LibRaw support for the exact camera model.
- Metadata copying is best-effort; review output metadata when its preservation is critical.
- CI integration fixtures do not cover every camera model or RAW extension.
