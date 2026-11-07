#!/usr/bin/env bash
set -Eeuo pipefail

IMAGE="${PHOTOLUT_GPU_TEST_IMAGE:-photolut:gpu-test}"
REPORT_DIR="${PHOTOLUT_GPU_REPORT_DIR:-artifacts/gpu-validation}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$REPORT_DIR"
REPORT="$REPORT_DIR/rtx-gpu-validation-$STAMP.log"

exec > >(tee "$REPORT") 2>&1

echo "PhotoLUT NVIDIA GPU integration validation"
echo "UTC timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Repository revision: $(git rev-parse HEAD 2>/dev/null || echo unknown)"
echo "Host: $(uname -a)"
echo "Docker client/server:"
docker version

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "ERROR: nvidia-smi is unavailable; install a supported NVIDIA driver on the host."
  exit 2
fi

echo
echo "NVIDIA GPU and driver:"
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv
nvidia-smi

echo
echo "Building the dedicated GPU integration image: $IMAGE"
docker build --target gpu-test --tag "$IMAGE" .

echo
echo "Running real NVDEC -> Vulkan/libplacebo -> NVENC integration tests."
echo "A missing/unusable GPU is a failure; this test does not silently fall back to CPU."
set +e
docker run --rm --gpus all \
  --env NVIDIA_DRIVER_CAPABILITIES=all \
  "$IMAGE"
TEST_STATUS=$?
set -e

echo
echo "GPU integration exit status: $TEST_STATUS"
echo "Validation log: $REPORT"
if [ "$TEST_STATUS" -ne 0 ]; then
  echo "RESULT: FAILED. Preserve this log with the host driver, GPU, and Docker versions."
  exit "$TEST_STATUS"
fi

echo "RESULT: PASSED. This validates GPU execution and output stream metadata."
echo "It does not replace playback review on the target HDR and SDR displays."
