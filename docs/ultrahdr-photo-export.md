# Ultra HDR photo export (experimental)

PhotoLUT accepts **single-page, RGB/RGBA, unsigned 16-bit TIFF** input and creates a backward-compatible Ultra HDR JPEG through Google's `ultrahdr_app` sample executable from [google/libultrahdr](https://github.com/google/libultrahdr). The Docker image builds libultrahdr v2.0.2 from pinned commit `e5f5a022fe96fc4dc2ee35c19f733a50df807abe` with `UHDR_BUILD_EXAMPLES=ON`. The upstream dual MIT/Apache-2.0 license is retained in the image at `/usr/share/doc/libultrahdr/LICENSE`.

The TIFF is interpreted as an SDR sRGB rendition. PhotoLUT reconstructs a highlight shoulder (default maximum content boost 4x), encodes a linear RGBA half-float HDR intent plus an SDR JPEG base, and asks libultrahdr to derive and embed the gain map. Both HDR and SDR intents are tagged with BT.709/sRGB primaries, and the configured maximum content boost is passed to the encoder as gain-map metadata. The output is probed by libultrahdr before it is accepted; the reported gain-map metadata must not exceed the requested maximum content boost or the export is rejected; the actual boost can be lower for images whose pixel values do not use the full configured range.

The feature is available through `POST /api/ultrahdr/export` and the dedicated Ultra HDR panel in the web UI. The endpoint accepts a TIFF upload, JPEG quality (1–100), and maximum content boost (>1–8). Uploads are limited to 200 MiB and images to 8 megapixels; temporary files are removed after the response. The 8-megapixel cap limits the number of simultaneously resident full-frame arrays; peak memory still depends on the input dimensions and encoder implementation.

**Input restrictions:** only RGB or fully opaque RGBA, contiguous, unsigned 16-bit TIFF is accepted. Big- and little-endian samples are supported, and TIFF orientation tags are applied before encoding. Multi-page, grayscale, planar-separate, transparent, and non-uint16 TIFF files are rejected. If an ICC profile is present, its RGB-to-sRGB color transform must be effectively identity; files without an embedded profile are treated as sRGB. Wide-gamut input must be converted to sRGB before export.

**Important:** this is inverse-tone-mapped HDR, not recovery of HDR data that was never present in an SDR TIFF. The reconstructed highlights are an estimated rendering. The feature remains experimental until representative photos have been visually reviewed on HDR-capable physical devices. Platform recompression may also alter or remove HDR metadata.

The CI workflow builds the pinned encoder, creates a high-highlight TIFF, performs a real Ultra HDR encode, verifies the gain-map metadata and configured boost ceiling, then decodes both the HDR linear half-float rendition and the SDR sRGB fallback and checks their pixel data. It also verifies the container runs unprivileged, smoke-tests the web UI/API schema, and runs the Python test suite. Run focused unit tests with `pytest tests/test_hdr_photo.py`.

For upstream build details, see the official [libultrahdr v2.0.2 build instructions](https://github.com/google/libultrahdr/blob/v2.0.2/docs/building.md). The official sample executable is named `ultrahdr_app`.

## Release validation checklist

The automated decode checks prove that the JPEG contains a decodable SDR base and HDR rendition; they do not prove that every gallery, browser, messaging app, or display renders it correctly. Before removing the experimental label, review a representative set of photos on at least one HDR-capable device and one SDR-only viewer:

1. Confirm the JPEG opens normally in an SDR viewer and that its base image has natural exposure and color.
2. Open the same file in an Ultra HDR-aware viewer on an HDR display. Check that reconstructed highlights are visible but not excessively bright, clipped, posterized, or surrounded by halos.
3. Compare neutral grays, saturated colors, shadow detail, and fine edges between the SDR and HDR presentations.
4. Copy the exported file through the intended sharing/storage workflow, then probe and decode the received copy again. Some services recompress JPEGs and may discard the gain map.
5. Record device model, OS version, viewer application/version, display mode, and the source/output pair used for review.

This checklist follows the platform's distinction between SDR base compatibility and HDR gain-map rendering. Android's [Ultra HDR implementation and validation guide](https://source.android.com/docs/core/camera/ultra-hdr) describes the reference implementation and device validation coverage, including JPEG_R and HDR-display test cases. Passing PhotoLUT CI alone must not be treated as equivalent to those device-level checks.
