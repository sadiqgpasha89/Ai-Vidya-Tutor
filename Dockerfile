# --- stage 1: download the front-end libraries (needs npm) ------------------------------------------------------
FROM node:22-slim AS vendor
WORKDIR /app
COPY scripts/vendor.sh scripts/vendor.sh
RUN mkdir -p frontend && sh -c 'cd /app && bash scripts/vendor.sh'

# --- stage 2: the app -----------------------------------------------------------------------------------------------
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 TEACHER_DATA_DIR=/data
# bubblewrap isolates student code runs; ffmpeg decodes microphone recordings for private speech recognition
RUN apt-get update && apt-get install -y --no-install-recommends bubblewrap ffmpeg curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements-voice.txt ./
RUN pip install -r requirements.txt -r requirements-voice.txt
COPY backend backend
COPY frontend frontend
COPY evals evals
COPY scripts scripts
COPY --from=vendor /app/frontend/vendor frontend/vendor
RUN useradd -m vidya && mkdir -p /data && chown -R vidya /data
USER vidya
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD curl -fs http://127.0.0.1:8000/api/health || exit 1
# One worker on purpose: the model queue, rate limits and SQLite writer are per process. Scale with a bigger model server instead.
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
