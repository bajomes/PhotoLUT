# PhotoLUT release validation

This checklist is the release record for the current PhotoLUT mainline, including RAW photo export, HLG/Rec.709 video export, and the experimental Ultra HDR TIFF-to-JPEG path.

## Automated gates

- [x] Full Python suite passes with pinned real RAW fixtures on PR head `12615d6a63bfd89915fda575aab967e134251a0d`: **170 passed, 1 skipped** in 71.09 s. The one skip is the real NVIDIA GPU integration test because the hosted runner lacks FFmpeg's custom `.cube` libplacebo option; this is not a GPU pass.
- [x] Docker production image builds from a clean checkout on PR head `12615d6a63bfd89915fda575aab967e134251a0d` (Actions run [#648](https://github.com/bajomes/PhotoLUT/actions/runs/42375813854)).
- [x] Container starts as the unprivileged `photolut` user and serves the UI and OpenAPI schema (Actions run [#648](https://github.com/bajomes/PhotoLUT/actions/runs/42375813854)).
- [x] Browser photo/export smoke checks pass in Actions run [#648](https://github.com/bajomes/PhotoLUT/actions/runs/42375813854), including the export and result-management flows.
- [x] `tests/browser_video_smoke.py` passes in Actions run [#648](https://github.com/bajomes/PhotoLUT/actions/runs/42375813854), covering HLG inspection, HLG/Rec.709 profile requests, preview controls, device status, and output naming.
- [x] Docker CI creates a real Ultra HDR output from a 16-bit TIFF, probes gain-map metadata, decodes both SDR and HDR renditions, and checks the configured boost ceiling (Actions run [#648](https://github.com/bajomes/PhotoLUT/actions/runs/42375813854)).
- [ ] Upload limits, malformed inputs, unsupported color profiles, timeout handling, cancellation, temporary-file cleanup, and concurrent processing limits are covered.
- [x] The pinned libultrahdr source revision and bundled dual MIT/Apache-2.0 license are verified in Docker CI run [#648](https://github.com/bajomes/PhotoLUT/actions/runs/42375813854).
- [ ] Dependency vulnerability audit via `pip-audit --strict -r requirements.txt` is now part of CI; record the result for the current head before release.

## Photo workflow acceptance

- [x] Automated RAW decode/export coverage includes Nikon NEF, Canon CR2/CR3, Sony a7 III ARW, and Fujifilm X-T4 RAF; the fixtures are checked against upstream SHA-256 sums. Camera-specific visual/metadata review and coverage of every intended model remain release checks.
- [ ] Confirm identity LUT output is visually neutral and creative LUT output matches the preview.
- [ ] Compare 16-bit TIFF pixel values and JPEG color/profile metadata.
- [ ] Verify output names, per-item deletion, format selection, ZIP contents, and a fresh batch after all results are removed.
- [ ] Confirm large batches stay within the documented upload, memory, and processing limits.

## Video workflow acceptance

Run on the target NVIDIA machine with a compatible NVIDIA driver, NVIDIA Container Toolkit, Vulkan, NVDEC, NVENC, and an FFmpeg build exposing libplacebo custom `.cube` LUT support. From the repository root, run `bash scripts/validate_nvidia_gpu.sh`; it builds the dedicated GPU test image, records GPU/driver/Docker details and the full test log under `artifacts/gpu-validation/`, and fails rather than silently skipping when the required runtime is unavailable. Preserve the generated log with the release evidence.

- [ ] Inspect representative HLG/BT.2020 10-bit source clips, including 4K30 and higher frame rates.
- [ ] Export HLG/BT.2020 using an HLG-authored LUT; verify HEVC Main 10 and output color tags.
- [ ] Export SDR/Rec.709 using a Rec.709-authored LUT; verify tone mapping occurs before LUT application and output is tagged SDR/BT.709.
- [ ] Confirm the application fails clearly when the required GPU pipeline is unavailable; no CPU fallback is allowed.
- [ ] Run `bash scripts/validate_nvidia_gpu.sh` on the target RTX 3050 host and attach its log to the release record.
- [ ] Play both exports on the intended editing and playback devices and inspect gradients, saturated colors, highlights, and shadow detail.

## Ultra HDR photo acceptance

The Ultra HDR path accepts only single-page, contiguous, unsigned 16-bit RGB or fully opaque RGBA TIFF within the documented 200 MiB / 8 MP limits. It treats the TIFF as SDR sRGB. Its HDR highlights are reconstructed estimates, not recovered capture data.

- [ ] Open the output in an SDR-only viewer and confirm the backward-compatible base image is correct.
- [ ] Open the output in an Ultra HDR-aware viewer on an HDR-capable display; inspect highlight intensity, clipping, banding, halos, neutral grays, saturated colors, shadows, and edges. Record the display model, certified VESA tier (if any), OS HDR mode, measured/claimed peak luminance, and viewer version; use VESA DisplayHDR Test or equivalent instrumented measurement where supported.
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

## Security and memory review

- [x] Uploads are streamed in 1 MiB chunks and checked against per-file and total request limits; photo/preview processing slots are acquired before writing uploads, preventing unlimited concurrent upload staging when workers are busy; output paths are constrained to the job output directory; subprocesses are invoked with argument arrays rather than shell interpolation; temporary output is cleaned on errors and cancellation paths are covered by tests.
- [x] Heavy RAW processing defaults to one active job (configurable up to two); LUT interpolation and image quantization use bounded tiles/row chunks; prior full-resolution buffers are released before the next RAW file is decoded.
- [ ] Record a peak-RSS stress run using the largest supported RAW dimensions and an 8 MP Ultra HDR TIFF, including concurrent upload pressure. The code-level review does not replace measurement on the deployment host.
- [ ] Complete the current-head dependency vulnerability audit and review any advisories before release.

## Open-source implementation references

- [google/libultrahdr](https://github.com/google/libultrahdr): reference gain-map encoder/decoder and backward-compatible SDR-base model. PhotoLUT pins a specific release/commit rather than tracking upstream main.
- [Android Open Source Project — Ultra HDR](https://source.android.com/docs/core/camera/ultra-hdr): platform implementation model and device-level validation guidance.
- [RawTherapee](https://github.com/RawTherapee/RawTherapee): reference for RAW compatibility expectations, color-managed processing, and camera-specific validation. PhotoLUT does not copy its GPL-3.0 code; this is an architectural/quality reference only.
- [FFmpeg libplacebo filter documentation](https://ffmpeg.org/ffmpeg-filters.html#libplacebo): GPU color conversion, tone mapping, and LUT processing reference.

Respect each upstream project's license. Do not copy GPL-licensed source into this MIT-licensed repository without an explicit license decision.


## Latest hosted CI evidence

- PR: [#62](https://github.com/bajomes/PhotoLUT/pull/62)
- Verified code head: `12615d6a63bfd89915fda575aab967e134251a0d` (run #648). Follow-up release tooling and CI security-audit commits are under a new CI run.
- Workflow: [Actions run #648](https://github.com/bajomes/PhotoLUT/actions/runs/42375813854) — both `test` and `docker-smoke` jobs succeeded.
- Python result: 170 passed, 1 skipped in 71.09 seconds. The skip is the hardware integration test because the hosted runner does not expose the required custom LUT option; it is explicitly not counted as GPU validation.
- Docker result: production and GPU-test images built; libultrahdr license check, real Ultra HDR encode/decode, unprivileged runtime, UI/API smoke, and browser photo/video checks passed.
- This hosted result does not prove RTX 3050 execution, physical display rendering, or compatibility with every camera model.
