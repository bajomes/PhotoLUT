#!/bin/sh
set -eu

# NVIDIA Container Toolkit injects the host driver's GLX ICD manifest and
# libraries at container start. On headless containers, the GLX ICD can fail
# Vulkan loader initialization even though the NVIDIA EGL ICD works. Reuse
# the injected manifest's driver API version, but point it at the EGL ICD.
NVIDIA_ICD_MANIFEST="/etc/vulkan/icd.d/nvidia_icd.json"
NVIDIA_EGL_LIBRARY="/usr/lib/libEGL_nvidia.so.0"
EGL_ICD_MANIFEST="/tmp/photolut-nvidia-egl-icd.json"

if [ -r "$NVIDIA_ICD_MANIFEST" ] \
    && [ -e "$NVIDIA_EGL_LIBRARY" ] \
    && [ -z "${VK_DRIVER_FILES:-${VK_ICD_FILENAMES:-}}" ]; then
    if python - "$NVIDIA_ICD_MANIFEST" "$NVIDIA_EGL_LIBRARY" "$EGL_ICD_MANIFEST" <<'PY'
import json
import pathlib
import sys

source, library, destination = map(pathlib.Path, sys.argv[1:])
manifest = json.loads(source.read_text(encoding="utf-8"))
icd = manifest.get("ICD")
if not isinstance(icd, dict) or not icd.get("api_version"):
    raise SystemExit("NVIDIA ICD manifest has no valid ICD api_version")
icd["library_path"] = str(library)
destination.write_text(
    json.dumps(manifest, indent=2) + "\n",
    encoding="utf-8",
)
PY
    then
        export VK_DRIVER_FILES="$EGL_ICD_MANIFEST"
        echo "PhotoLUT: using NVIDIA EGL Vulkan ICD ($NVIDIA_EGL_LIBRARY)" >&2
    else
        echo "PhotoLUT: could not prepare NVIDIA EGL ICD; retaining default Vulkan ICD configuration" >&2
    fi
fi

exec "$@"
