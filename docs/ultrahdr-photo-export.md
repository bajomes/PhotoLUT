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
derive and embed the gain map. The output is probed by libultrahdr before it
is accepted.

**Input restrictions:** only RGB or fully opaque RGBA, contiguous, unsigned
16-bit TIFF is accepted. Multi-page, grayscale, planar-separate, transparent,
and non-uint16 TIFF files are rejected. If an ICC profile is present, it must
be identifiable as sRGB; files without an embedded profile are treated as
sRGB. Wide-gamut input must be converted to sRGB before export.

**Important:** this is inverse-tone-mapped HDR, not recovery of HDR data that
was never present in an SDR TIFF. The reconstructed highlights are an
estimated rendering and should be reviewed visually on an HDR-capable display.
The current implementation is experimental and is not yet wired into the web
UI.

Run unit tests with `pytest tests/test_hdr_photo.py`. To build the upstream
encoder, use the official
[libultrahdr build instructions](https://github.com/google/libultrahdr/blob/v2.0.2/docs/building.md).
The v2.0.2 release is pinned at commit
`e5f5a022fe96fc4dc2ee35c19f733a50df807abe`; on Linux the documented build
uses CMake, a C++17 compiler, libjpeg development headers, and Ninja. The
official sample executable is named `ultrahdr_app`. The actual command-line
argument compatibility and end-to-end gain-map output still need to be
verified against that pinned build before this export is enabled in the app.
