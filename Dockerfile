FROM python:3.12-slim AS ultrahdr-builder

ARG LIBULTRAHDR_COMMIT=e5f5a022fe96fc4dc2ee35c19f733a50df807abe

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates cmake git libjpeg-dev ninja-build pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp/libultrahdr
RUN git init . \
    && git remote add origin https://github.com/google/libultrahdr.git \
    && git fetch --depth 1 origin "${LIBULTRAHDR_COMMIT}" \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "${LIBULTRAHDR_COMMIT}"

RUN cmake -S . -B build -G Ninja \
      -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX=/opt/ultrahdr \
      -DUHDR_BUILD_EXAMPLES=ON \
      -DUHDR_ENABLE_HEIF=OFF \
    && cmake --build build --parallel \
    && cmake --install build \
    && test -x /opt/ultrahdr/bin/ultrahdr_app

FROM python:3.12-slim-trixie AS runtime

RUN echo "deb http://deb.debian.org/debian sid main" > /etc/apt/sources.list.d/sid.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        libraw-dev \
        libimage-exiftool-perl \
        libvulkan1 \
        libjpeg62-turbo \
        ffmpeg/sid \
    && ffmpeg -hide_banner -filters 2>&1 | grep -q libplacebo \
    && ffmpeg -hide_banner -filters 2>&1 | grep -q zscale \
    && ffmpeg -hide_banner -filters 2>&1 | grep -q psnr \
    && ffmpeg -hide_banner -encoders 2>&1 | grep -q libx265 \
    && ffmpeg -hide_banner -h filter=libplacebo 2>&1 | grep -Eq '^[[:space:]]*lut[[:space:]]+<' \
    && ffmpeg -hide_banner -encoders 2>&1 | grep -q hevc_nvenc \
    && ffmpeg -hide_banner -hwaccels 2>&1 | grep -q '^cuda$' \
    && ffmpeg -hide_banner -init_hw_device list 2>&1 | grep -q vulkan \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ultrahdr-builder /opt/ultrahdr/bin/ultrahdr_app /usr/local/bin/ultrahdr_app
COPY --from=ultrahdr-builder /opt/ultrahdr/lib/ /usr/local/lib/
COPY --from=ultrahdr-builder /tmp/libultrahdr/LICENSE /usr/share/doc/libultrahdr/LICENSE
RUN ldconfig

RUN groupadd --system photolut && useradd --system --gid photolut --home-dir /app --no-create-home photolut

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py core.py jobs.py video.py hdr_photo.py ./
COPY static/ static/

ENV PHOTOLUT_WORK_DIR=/var/lib/photolut/jobs
RUN mkdir -p /var/lib/photolut/jobs && chown -R photolut:photolut /var/lib/photolut
USER photolut

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

 
FROM runtime AS gpu-test
USER root
RUN pip install --no-cache-dir pytest
COPY --chown=photolut:photolut tests/test_video_integration.py /app/tests/test_video_integration.py
USER photolut
CMD ["python", "-m", "pytest", "-q", "-rs", "/app/tests/test_video_integration.py"]

FROM runtime AS final
