# PhotoLUT dependency license inventory

**Generated from:** `requirements-dev.lock`  
**Verification:** GitHub Actions run [#43406341760](https://github.com/bajomes/PhotoLUT/actions/runs/43406341760), Python 3.12 Linux  
**Inventory result:** 27/27 locked Python distributions were installed at the exact pinned versions; all 27 exposed a license expression or license metadata. No lock/install mismatches and no packages with both license fields absent were reported.

This is an inventory of Python distributions in the development lock (runtime plus test tooling). It is not a legal opinion and does not replace review of the actual license texts, notices, bundled native libraries, or redistribution conditions.

| Distribution | Version | Declared license metadata |
|---|---:|---|
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.16.0 | MIT |
| click | 8.5.1 | BSD-3-Clause |
| fastapi | 0.162.0 | MIT |
| h11 | 0.16.0 | MIT |
| idna | 3.20 | BSD-3-Clause |
| numpy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| opentelemetry-api | 1.45.2 | Apache-2.0 |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pillow | 13.0.0 | MIT-CMU |
| pydantic | 2.14.3 | MIT |
| pydantic-core | 2.50.4 | MIT |
| python-multipart | 0.0.32 | Apache-2.0 |
| rawpy | 0.27.1 | MIT |
| starlette | 1.10.0 | BSD-3-Clause |
| tifffile | 2026.10.15 | BSD-3-Clause |
| truststore | 0.10.5 | MIT |
| typing-extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.5 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |
| httpcore2 | 2.16.0 | BSD-3-Clause |
| httpx2 | 2.16.0 | BSD-3-Clause |
| iniconfig | 2.3.1 | MIT |
| pluggy | 1.7.0 | MIT |
| pygments | 2.21.0 | BSD-2-Clause |
| pytest | 9.2.0 | MIT |

## Remaining inventory and review

The following are not covered by the Python lock report and must be inventoried separately before declaring the complete dependency-license gate passed:

- Debian base image and all installed OS packages for the `photo` target, including LibRaw and ExifTool.
- Debian Sid packages in the `video` target, including FFmpeg, libplacebo, Vulkan loader/runtime and their transitive shared-library dependencies.
- License texts, copyright notices, attribution and source-offer/redistribution obligations required by the exact package builds and FFmpeg configuration.
- Third-party browser/runtime assets shipped or fetched by the application, if any.

The CI report tool is `scripts/audit_dependency_licenses.py`. It checks exact installed versions against a selected requirements lock and prints package license metadata/classifiers. It intentionally does not infer legal compatibility from classifiers. DOC-01 remains **IN PROGRESS** until the system-package inventory and notice review are completed.
