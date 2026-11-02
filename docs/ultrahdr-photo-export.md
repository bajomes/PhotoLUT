# Ultra HDR photo export (experimental)

PhotoLUT's first Ultra HDR photo-export slice accepts **single-page, RGB/RGBA,
unsigned 16-bit TIFF** input and creates a backward-compatible Ultra HDR JPEG.
It requires Google's `ultrahdr_app` sample executable from
[google/libultrahdr](https://github.com/google/libultrahdr) on PATH. The
upstream build documented for libultrahdr v2.0.2 produces this executable
when `UHDR_BUILD_EXAMPLES=ON` (the default).

The TIFF is interpreted as an SDR sRGB rendition. PhotoLUT reconstructs a
highlight shoulder (default maximum content boost 4x), encodes a linear
RGBA half-float HDR intent plus an SDR JPEG base, and asks libultrahdr to
derive and embed the gain map. Both HDR and SDR intents are explicitly tagged
with BT.709/sRGB primaries, and the configured maximum content boost is passed
to the encoder as gain-map metadata. The output is probed by libultrahdr before
it is accepted.

**Input restrictions:** only RGB or fully opaque RGBA, contiguous, unsigned
16-bit TIFF is accepted. Multi-page, grayscale, planar-separate, transparent,
and non-uint16 TIFF files are rejected. If an ICC profile is present, it must
be identifiable as sRGB; files without an embedded profile are treated as
sRGB. Wide-gamut input must be converted to sRGB before export.

**Important:** this is inverse-tone-mapped HDR, not recovery of HDR data that
was never present in an SDR TIFF. The reconstructed highlights are an
estimated rendering and should be reviewed visually on an HDR-capable display.
The experimental exporter is available in a separate web UI panel and API endpoint (`POST /api/ultrahdr/export`). Upload a `.tif` or `.tiff` file as `tiff_file`; optional form fields are `quality` (1–100, default 95) and `max_boost` (greater than 1 and at most 8, default 4). The API enforces a 200 MiB upload limit and an 80-megapixel decoded-image limit, returns an `image/jpeg` download only after gain-map verification, and removes its temporary files after the response is sent. Busy processing returns 429; missing encoder returns 503; invalid TIFF or encoder failures return a client error.

The API has dedicated tests in `tests/test_ultrahdr_api.py`; run the suite with `pytest -q`. To build the upstream
encoder, use the official
[libultrahdr build instructions](https://github.com/google/libultrahdr/blob/v2.0.2/docs/building.md).
The v2.0.2 release is pinned at commit
`e5f5a022fe96fc4dc2ee35c19f733a50df807abe`; on Linux the documented build
uses CMake, a C++17 compiler, libjpeg development headers, and Ninja. The
official sample executable is named `ultrahdr_app`. The command-line flags used by the exporter have been checked against the v2.0.2
sample source. The pinned Docker build and a real TIFF-to-Ultra-HDR gain-map integration smoke test run in GitHub Actions. The web export remains experimental pending visual review on HDR-capable devices.
