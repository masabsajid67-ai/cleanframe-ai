FROM python:3.12-slim

# FFmpeg is required for probe + audio mux. No GPU in this image: the CPU
# engine runs here; ProPainter runs on RunPod (see GPU.md).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

ENV CLEANFRAME_STORAGE_DIR=/data \
    HOST=0.0.0.0 \
    PORT=8000
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
