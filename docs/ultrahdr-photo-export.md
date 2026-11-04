# Ultra HDR photo export (experimental)

PhotoLUT accepts **single-page, RGB/RGBA, unsigned 16-bit TIFF** input and creates a backward-compatible Ultra HDR JPEG through Google's `ultrahdr_app` sample executable from [google/libultrahdr](https://github.com/google/libultrahdr). The Docker image builds libultrahdr v2.0.2 from pinned commit `e5f5a022fe96fc4dc2ee35c19f733a50df807abe` with `UHDR_BUILD_EXAMPLES=ON`.

The TIFF is interpreted as an SDR sRGB rendition. PhotoLUT reconstructs a highlight shoulder (default maximum content boost 4x), encodes a linear RGBA half-float HDR intent plus an SDR JPEG base, and asks libultrahdr to derive and embed the gain map. Both HDR and SDR intents are tagged with BT.709/sRGB primaries, and the configured maximum content boost is passed to the encoder as gain-map metadata. The output is probed by libultrahdr before it is accepted.

The feature is available through `POST /api/ultrahdr/export` and the dedicated Ultra HDR panel in the web UI. The endpoint accepts a TIFF upload, JPEG quality (1–100), and maximum content boost (>1–8). Uploads are limited to 200 MiB and images to 8 megapixels; temporary files are removed after the response. The 8-megapixel cap limits the number of simultaneously resident full-frame arrays; peak memory still depends on the input dimensions and encoder implementation.

**Input restrictions:** only RGB or fully opaque RGBA, contiguous, unsigned 16-bit TIFF is accepted. Multi-page, grayscale, planar-separate, transparent, and non-uint16 TIFF files are rejected. If an ICC profile is present, its RGB-to-sRGB color transform must be effectively identity; files without an embedded profile are treated as sRGB. Wide-gamut input must be converted to sRGB before export.

**Important:** this is inverse-tone-mapped HDR, not recovery of HDR data that was never present in an SDR TIFF. The reconstructed highlights are an estimated rendering. The feature remains experimental until representative photos have been visually reviewed on HDR-capable physical devices. Platform recompression may also alter or remove HDR metadata.

The CI workflow builds the pinned encoder, runs a real TIFF-to-Ultra-HDR encode and gain-map probe in the Docker image, verifies the container runs unprivileged, smoke-tests the web UI/API schema, and runs the Python test suite. Run focused unit tests with `pytest tests/test_hdr_photo.py`.

For upstream build details, see the official [libultrahdr v2.0.2 build instructions](https://github.com/google/libultrahdr/blob/v2.0.2/docs/building.md). The official sample executable is named `ultrahdr_app`.
