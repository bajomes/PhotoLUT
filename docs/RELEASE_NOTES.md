# PhotoLUT — release candidate notes

Status: release candidate under validation; not a final release.

## Included

- RAW photo processing with 3D .cube LUTs, 16-bit TIFF and JPEG export, sRGB profile embedding, and metadata-copy attempt through ExifTool.
- Batch results with per-item removal and JPEG/TIFF/combined ZIP download choices.
- HLG/BT.2020 video inspection and GPU-only HEVC Main 10 export using NVDEC, Vulkan/libplacebo LUT processing, and NVENC.
- HLG/BT.2020 output for HLG-authored LUTs, or HLG-to-SDR BT.709 tone mapping followed by a Rec.709 LUT for standard SDR delivery.
- Experimental Ultra HDR JPEG generation from supported 16-bit sRGB TIFF files using pinned Google libultrahdr v2.0.2.
- Docker Compose deployment bound to localhost by default, with Linux/macOS shell and Windows PowerShell installation helpers.

## Verification recorded on 7 November 2026

- PR head 12615d6a63bfd89915fda575aab967e134251a0d: GitHub Actions run #648 succeeded.
- Python suite: 170 passed, 1 skipped. The skip is the real NVIDIA GPU integration test because the hosted runner lacks the required FFmpeg custom .cube libplacebo support.
- Docker production and GPU-test image builds passed.
- Real Ultra HDR TIFF encode, gain-map probe, HDR/SDR decode checks, license check, unprivileged container check, UI/API smoke, and browser smoke checks passed.

## Known release gates

- Run bash scripts/validate_nvidia_gpu.sh on the target RTX 3050 host; retain its report.
- Review HLG output on a physical HDR display and Rec.709 output on a standard SDR display.
- Review Ultra HDR output on an HDR-capable device and an SDR-only viewer, including after the intended sharing/storage workflow.
- Record RAW compatibility for every camera model in the first-release support list. Existing automated fixtures cover two Nikon NEF samples and one Canon CR2 sample; this is not universal camera certification.
- Complete dependency/security review and final release record.

## Limitations

- Ultra HDR highlights are reconstructed from SDR pixels; they are not recovered HDR capture data.
- HLG video processing accepts confirmed HLG/BT.2020/10-bit sources only. Dolby Vision and PQ/HDR10 grading are not enabled.
- Video GPU processing requires a compatible NVIDIA driver, NVIDIA Container Toolkit, Vulkan, NVDEC/NVENC, and FFmpeg with libplacebo custom .cube LUT support.
- RAW demosaicing and photo LUT processing are CPU-based. GPU passthrough currently accelerates the video path only.
- Processed TIFF/JPEG files are rendered images; not all camera-specific RAW metadata can be preserved meaningfully.

Do not publish these notes as a final release announcement until all release gates have recorded evidence.
