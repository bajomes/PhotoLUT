FROM python:3.12-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS photo

ARG DEBIAN_SNAPSHOT=20261113T000000Z

# The default photo image contains only the native libraries required for RAW
# decoding and metadata handling. It deliberately has no FFmpeg/Vulkan stack.
# Replace the base image's moving Debian mirrors with a fixed archive snapshot.
RUN set -eux; \
    printf '%s\n' \
      'Types: deb' \
      "URIs: https://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}" \
      'Suites: trixie trixie-updates' \
      'Components: main' \
      'Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg' \
      '' \
      'Types: deb' \
      "URIs: https://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT}" \
      'Suites: trixie-security' \
      'Components: main' \
      'Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg' \
      > /etc/apt/sources.list.d/debian.sources; \
    apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get -o Acquire::Check-Valid-Until=false install -y --no-install-recommends \
        libraw-dev \
        libimage-exiftool-perl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system photolut && useradd --system --gid photolut --home-dir /app --no-create-home photolut

WORKDIR /app

COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

COPY app.py core.py jobs.py video.py ./
COPY static/ static/

ENV PHOTOLUT_WORK_DIR=/var/lib/photolut/jobs
RUN mkdir -p /var/lib/photolut/jobs && chown -R photolut:photolut /var/lib/photolut
USER photolut

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]


# Optional video/GPU image. This stage adds the FFmpeg/libplacebo, Vulkan and
# NVIDIA encoder/runtime tooling required by the separate HLG video workflow.
FROM photo AS video

USER root
RUN echo "deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT} sid main" > /etc/apt/sources.list.d/sid.list \
    && apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get -o Acquire::Check-Valid-Until=false install -y --no-install-recommends libvulkan1 ffmpeg/sid \
    && ffmpeg -hide_banner -filters 2>&1 | grep -q libplacebo \
    && ffmpeg -hide_banner -h filter=libplacebo 2>&1 | grep -Eq '^[[:space:]]*lut[[:space:]]+<' \
    && ffmpeg -hide_banner -encoders 2>&1 | grep -q hevc_nvenc \
    && ffmpeg -hide_banner -hwaccels 2>&1 | grep -q '^cuda$' \
    && ffmpeg -hide_banner -init_hw_device list 2>&1 | grep -q vulkan \
    && rm -rf /var/lib/apt/lists/*
USER photolut
