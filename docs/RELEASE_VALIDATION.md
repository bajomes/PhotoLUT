# PhotoLUT release validation

This checklist is the release record for the current PhotoLUT mainline, including RAW photo export, HLG/Rec.709 video export, and the experimental Ultra HDR TIFF-to-JPEG path.

## Automated gates

- [ ] Full Python suite passes with the pinned real RAW fixtures present; record the exact commit and test summary.
- [ ] Docker production image builds from a clean checkout.
- [ ] Container starts as the unprivileged `photolut` user and serves the UI and OpenAPI schema.
- [ ] Browser smoke covers photo preview, batch export, result deletion, remaining-result state, JPEG/TIFF/ZIP selection, and the empty state.
- [ ] Browser smoke covers video inspection, HLG/Rec.709 LUT-profile selection, comparison playback, and export UI.
- [ ] Ultra HDR integration creates a JPEG_R-compatible output from a known 16-bit TIFF; decode and verify both SDR base and HDR rendition, gain-map metadata, ICC profile, and configured maximum content boost.
- [ ] Upload limits, malformed inputs, unsupported color profiles, timeout handling, cancellation, temporary-file cleanup, and concurrent processing limits are covered.
- [ ] Review dependency and container build changes; preserve third-party licenses and pinned source revisions.

## Photo workflow acceptance

- [ ] Test representative RAW files from every camera model intended for the first release, including portrait and landscape orientation.
- [ ] Confirm identity LUT output is visually neutral and creative LUT output matches the preview.
- [ ] Compare 16-bit TIFF pixel values and JPEG color/profile metadata.
- [ ] Verify output names, per-item deletion, format selection, ZIP contents, and a fresh batch after all results are removed.
- [ ] Confirm large batches stay within the documented upload, memory, and processing limits.

## Video workflow acceptance

Run on the target NVIDIA machine with a compatible NVIDIA driver, NVIDIA Container Toolkit, Vulkan, NVDEC, NVENC, and an FFmpeg build exposing libplacebo custom `.cube` LUT support.

- [ ] Inspect representative HLG/BT.2020 10-bit source clips, including 4K30 and higher frame rates.
- [ ] Export HLG/BT.2020 using an HLG-authored LUT; verify HEVC Main 10 and output color tags.
- [ ] Export SDR/Rec.709 using a Rec.709-authored LUT; verify tone mapping occurs before LUT application and output is tagged SDR/BT.709.
- [ ] Confirm the application fails clearly when the required GPU pipeline is unavailable; no CPU fallback is allowed.
- [ ] Play both exports on the intended editing and playback devices and inspect gradients, saturated colors, highlights, and shadow detail.

## Ultra HDR photo acceptance

The Ultra HDR path accepts only single-page, contiguous, unsigned 16-bit RGB or fully opaque RGBA TIFF within the documented 200 MiB / 8 MP limits. It treats the TIFF as SDR sRGB. Its HDR highlights are reconstructed estimates, not recovered capture data.

- [ ] Open the output in an SDR-only viewer and confirm the backward-compatible base image is correct.
- [ ] Open the output in an Ultra HDR-aware viewer on an HDR-capable display; inspect highlight intensity, clipping, banding, halos, neutral grays, saturated colors, shadows, and edges.
- [ ] Record device model, OS version, viewer/version, display mode, source TIFF, and exported JPEG.
- [ ] Copy/share the JPEG through the intended delivery service; verify whether the gain map survives recompression and download.
- [ ] Keep the feature marked experimental until this device-level review is recorded.

## Release record

Record the following before publishing a final release:

- Release tag and exact Git commit:
- GitHub Actions run URL and conclusion:
- Python test summary:
- Docker/browser smoke result:
- Target GPU model, driver, Vulkan device, FFmpeg version, and HLG/Rec.709 results:
- HDR-capable device, OS, viewer, and Ultra HDR visual-review result:
- Known limitations and camera models tested:
- Release date and reviewer:

A green hosted CI run proves only the checks executed by that workflow. It does not substitute for the target NVIDIA GPU test or physical HDR-display review.

## Open-source implementation references

- [google/libultrahdr](https://github.com/google/libultrahdr): reference gain-map encoder/decoder and backward-compatible SDR-base model. PhotoLUT pins a specific release/commit rather than tracking upstream main.
- [Android Open Source Project — Ultra HDR](https://source.android.com/docs/core/camera/ultra-hdr): platform implementation model and device-level validation guidance.
- [RawTherapee](https://github.com/RawTherapee/RawTherapee): reference for RAW compatibility expectations, color-managed processing, and camera-specific validation. PhotoLUT does not copy its GPL-3.0 code; this is an architectural/quality reference only.
- [FFmpeg libplacebo filter documentation](https://ffmpeg.org/ffmpeg-filters.html#libplacebo): GPU color conversion, tone mapping, and LUT processing reference.

Respect each upstream project's license. Do not copy GPL-licensed source into this MIT-licensed repository without an explicit license decision.
