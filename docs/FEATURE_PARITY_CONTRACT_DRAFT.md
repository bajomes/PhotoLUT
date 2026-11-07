# PhotoLUT Feature-Parity Contract — Draft for Product Decision

**Status:** DRAFT — no parity feature has been accepted, excluded, or declared complete by this document.  
**Applies to:** Gate B only. Gate A / PhotoLUT 1.1.0 remains independently governed by `RELEASE_SCOPE_AND_ACCEPTANCE.md`.

## 1. Decision boundary

The comparison products and exact versions/platforms must be frozen by the product owner before implementation. Official documentation is used to describe comparison workflows; it does not imply PhotoLUT has those capabilities. Rows below are deliberately retained until an explicit target decision is recorded. Difficulty or cost is not a reason to silently remove a row.

## 2. Candidate workflow matrix

| ID | Comparison product / version | Workflow | Measurable behavior to contract | Current PhotoLUT condition | Implementation required if selected | Acceptance test | Status |
|---|---|---|---|---|---|---|---|
| P-F01 | Lightroom Classic / version TBD | RAW development | Decode supported camera RAW; deterministic demosaic, WB and output profile | RAW decode to rendered sRGB using camera WB; no interactive develop controls | Define camera matrix, WB controls, demosaic options, color pipeline and supported-camera list | Per-camera RAW fixture, reference patches, metadata and output checks | BELUM DISEPAKATI |
| P-F02 | Lightroom Classic / version TBD | Nondestructive editing | Edits stored as reversible parameters; original source unchanged; reopen session reproduces render | Batch output only; no edit document or session persistence | Versioned edit graph/document, persistence, renderer and migration rules | Save/reopen/re-render checksum and original-file immutability | BELUM DISEPAKATI |
| P-F03 | Lightroom Classic / version TBD | Exposure / contrast / WB / highlights / shadows | Numeric controls with defined units, order, clipping and neutral-point behavior | Not implemented; LUT-only creative transform | Linear-light or scene-referred parameter model, WB adaptation and tone controls | Analytic ramps, neutral patches, clipping and reference comparisons | BELUM DISEPAKATI |
| P-F04 | Lightroom Classic / version TBD | Curves and HSL | Point/parametric curves and hue/saturation/luminance ranges with predictable interpolation | Not implemented | Curve editor, HSL model, gamut handling and serialization | Dense ramp, hue sweep, boundary and round-trip tests | BELUM DISEPAKATI |
| P-F05 | Lightroom Classic / version TBD | Crop / rotate | Aspect presets, arbitrary crop, rotate/straighten, orientation-aware output | No editing crop/rotate; decoder/export normalizes orientation | Geometry model, preview transform, resampling and metadata policy | Geometry fixtures, orientation matrix, edge and dimension checks | BELUM DISEPAKATI |
| P-F06 | Lightroom Classic / version TBD | Undo / redo | Ordered reversible edit operations; stable undo/redo boundaries | Not implemented | Command/history model tied to nondestructive project state | Property-based operation sequences and save/reopen history | BELUM DISEPAKATI |
| P-F07 | Lightroom Classic / version TBD | Presets | Save, apply, update, import/export parameter presets | Imports .cube LUT only; no parameter presets | Versioned preset schema, compatibility and batch application | Preset round-trip, compatibility and deterministic render | BELUM DISEPAKATI |
| P-F08 | Lightroom Classic / version TBD | Batch | Apply settings to selected photos; independent per-file progress/failure | RAW batch and LUT are implemented | If parity requires sync of arbitrary edit settings, add edit-state propagation | Mixed-validity batch, per-file parity and retry tests | BELUM DISEPAKATI |
| P-F09 | Lightroom Classic / version TBD | Export | Format, dimensions, bit depth, profile, metadata and naming controls | JPEG quality 95 and RGB TIFF 16-bit; sRGB ICC; best-effort descriptive metadata | Export configuration schema, color conversion and metadata policy | File signature, pixel depth, ICC, EXIF/XMP, dimensions and naming checks | BELUM DISEPAKATI |
| P-L01 | Lightroom Classic / version TBD | Local masking / selective adjustment | Subject/linear/radial masks with feathering and adjustable local parameters | Not implemented | Mask representation, raster/vector evaluation, compositing and UI | Synthetic mask geometry, feather profile, edge leakage and render tests | BELUM DISEPAKATI |
| P-L02 | Lightroom Classic / version TBD | Healing / object removal | Sample/patch-based repair with source and target region behavior | Not implemented | Patch synthesis/inpainting engine, interaction and edit persistence | Known-defect image set, seam/texture review and undo tests | BELUM DISEPAKATI |
| P-L03 | Lightroom Classic / version TBD | Sharpening / denoise | Defined radius/detail/masking and luminance/chroma noise behavior | No user controls; LibRaw FBDD noise reduction disabled | Select processing engine and parameter model; preserve source bit depth | Slanted-edge, noise-chart and artifact metrics plus visual review | BELUM DISEPAKATI |
| P-G01 | DaVinci Resolve / version TBD | LUT and color transforms | Declared input/output color spaces, transfer functions, LUT domain, interpolation and transform order | 3D .cube; current photo path sRGB; trilinear interpolation; linear-light intensity mix | Explicit input/output transform graph, metadata/profile validation and UI | Known color patches, analytic LUTs, clipping/domain tests and round-trip | BELUM DISEPAKATI |
| P-G02 | DaVinci Resolve / version TBD | Color management | Project/input/output spaces, display transform and managed monitoring | Fixed sRGB output path; no configurable project color management | Color-management architecture, profile registry and transform engine | ICC/OCIO reference fixtures, round-trip and output-tag checks | BELUM DISEPAKATI |
| P-G03 | DaVinci Resolve / version TBD | Scopes | Histogram, waveform, vectorscope and RGB parade based on displayed/working signal | Not implemented | Correct signal tap, scope math, overlays and UI | Synthetic signals with expected bins/trace coordinates | BELUM DISEPAKATI |
| P-G04 | DaVinci Resolve / version TBD | HDR / wide gamut | Declared HDR transfer/gamut, mastering metadata, display transform and highlight handling | Still-photo HDR/wide-gamut excluded from 1.1.0 | Scene/display-referred pipeline, HDR export, metadata and compatible display path | PQ/HLG/BT.2020 patches, metadata inspection and HDR display review | BELUM DISEPAKATI |
| P-V01 | DaVinci Resolve or Kdenlive / version TBD | Multitrack timeline | Multiple independently editable video/audio tracks with timebase and clip placement | Not implemented; existing video path is single-source batch processing | Timeline model, media graph, persistence, playback engine and UI | Multi-track fixture project, edit/reopen and timeline render | BELUM DISEPAKATI |
| P-V02 | DaVinci Resolve or Kdenlive / version TBD | Trim / split / transitions | Frame-accurate edits, ripple behavior, transitions and overlap rules | Not implemented | Nonlinear edit model, frame-accurate time arithmetic and transition compositor | Frame-index boundary and transition golden renders | BELUM DISEPAKATI |
| P-V03 | DaVinci Resolve or Kdenlive / version TBD | Keyframes | Time-varying clip/effect parameters with interpolation/easing | Not implemented | Animation curves, interpolation, UI and persistence | Exact keyframe sample values and rendered frame checks | BELUM DISEPAKATI |
| P-V04 | DaVinci Resolve or Kdenlive / version TBD | Audio | Multitrack audio, gain, fades, meters, mixing and export | No audio editing or mixing | Audio graph, sync/timebase, mixer, codecs and render integration | Tone, sync, clipping, channel-layout and export tests | BELUM DISEPAKATI |
| P-V05 | DaVinci Resolve or Kdenlive / version TBD | Proxy media | Generate/manage lower-resolution media and relink originals | Not implemented | Proxy lifecycle, cache invalidation, relink and storage policy | Proxy/original relink, frame correspondence and offline tests | BELUM DISEPAKATI |
| P-V06 | DaVinci Resolve or Kdenlive / version TBD | Project storage | Save/reopen project with media references and version migration | Not implemented; job state is in-memory and temporary | Persistent project schema, atomic saves, asset relinking and migrations | Save/reopen, crash recovery, migration and missing-media tests | BELUM DISEPAKATI |
| P-V07 | DaVinci Resolve or Kdenlive / version TBD | Render | Timeline render with codec, profile, bit depth, audio and progress controls | Existing optional HLG video batch transcode only; no timeline | Render graph, queue, cancellation, codec/profile validation and durable outputs | Golden media fixtures, ffprobe metadata, decode and quality metrics | BELUM DISEPAKATI |

## 3. Current PhotoLUT facts relevant to the contract

- PhotoLUT 1.1.0 release scope is a RAW batch processor with 3D `.cube` LUT, intensity, preview, JPEG and 16-bit TIFF export.
- The still-photo decoder emits rendered sRGB RGB data; this is not a scene-linear RAW development pipeline.
- The still-photo LUT path uses the parsed 3D LUT domain and trilinear interpolation, clamps output to [0, 1], and blends LUT intensity in linear-light sRGB.
- Preview uses a reduced-resolution RAW decode and JPEG proxy. It is not pixel-identical to full-resolution export.
- The job registry is process-local memory; completed outputs are temporary and are not restored after container recreation.
- The existing video path is an optional hardware-gated HLG batch pipeline, not a nonlinear editor.

These are implementation observations, not a promise of parity.

## 4. Official comparison references consulted

- Adobe Lightroom Classic Develop module: https://helpx.adobe.com/lightroom-classic/desktop/help/applying-adjustments-develop-module-basic.html
- Adobe Lightroom Classic presets: https://helpx.adobe.com/lightroom-classic/desktop/process-and-develop-photos/apply-presets.html
- Kdenlive 26.08 timeline: https://docs.kdenlive.org/en/user_interface/timeline.html
- Kdenlive effects and filters: https://docs.kdenlive.org/en/effects_and_filters.html
- Kdenlive rendering: https://docs.kdenlive.org/en/cutting_and_assembling/exporting.html

Exact product versions, platform and official references for Snapseed and DaVinci Resolve remain to be frozen/verified after the product decision. Do not infer version parity from these references.

## 5. Product decision required

Before marking any row mandatory or optional, record:
1. Which comparator(s) are contractual: Lightroom Classic, Snapseed, DaVinci Resolve, Kdenlive (one or multiple)?
2. Exact comparator version(s), operating system(s), and desktop/mobile/web platform(s)?
3. Which workflows are mandatory for Gate B, and which are explicitly optional? If multiple products are selected, is parity required against every listed workflow or only named subsets?
4. What measurable reference fixtures and tolerance policy should govern visual/color comparisons?

Until those decisions are recorded, all Gate B rows remain **BELUM DISEPAKATI**. No parity scope has been removed.
