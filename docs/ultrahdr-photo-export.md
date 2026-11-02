# Ultra HDR photo export (experimental)

PhotoLUT's first Ultra HDR photo-export slice accepts **single-page, RGB/RGBA,
unsigned 16-bit TIFF** input and creates a backward-compatible Ultra HDR JPEG.
It requires Google's `uhdr_app` executable from
[google/libultrahdr](https://github.com/google/libultrahdr) on PATH.

The TIFF is interpreted as an SDR sRGB rendition. PhotoLUT reconstructs a
highlight shoulder (default maximum content boost 4x), encodes a linear
RGBA half-float HDR intent plus an SDR JPEG base, and asks libultrahdr to
derive and embed the gain map. The output is probed by libultrahdr before it
is accepted.

**Important:** this is inverse-tone-mapped HDR, not recovery of HDR data that
was never present in an SDR TIFF. Wide-gamut TIFF input is not color-managed
in this first slice; use sRGB TIFF sources only. Multi-page, grayscale, and
non-uint16 TIFF files are rejected rather than silently converted.

Run tests with `pytest tests/test_hdr_photo.py`. Install/build libultrahdr
separately and ensure `uhdr_app` is available on PATH before using the
export function. This experimental slice is not yet wired into the web UI.
