FROM python:3.12-slim-trixie

RUN echo "deb http://deb.debian.org/debian sid main" > /etc/apt/sources.list.d/sid.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        libraw-dev \
        libimage-exiftool-perl \
        libvulkan1 \
        ffmpeg/sid \
    && ffmpeg -hide_banner -filters 2>&1 | grep -q libplacebo \
    && ffmpeg -hide_banner -h filter=libplacebo 2>&1 | grep -q lut \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system photolut && useradd --system --gid photolut --home-dir /app --no-create-home photolut

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py core.py jobs.py video.py ./
COPY static/ static/

ENV PHOTOLUT_WORK_DIR=/var/lib/photolut/jobs
RUN mkdir -p /var/lib/photolut/jobs && chown -R photolut:photolut /var/lib/photolut
USER photolut

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]