"""CLEANFRAME AI — FastAPI backend.

One function only: remove captions/subtitles from a video.
Endpoints (all under /api):
    GET    /api/health
    POST   /api/jobs/upload            multipart field `video`
    GET    /api/jobs/{id}              status / progress / detection
    POST   /api/jobs/{id}/detect       run OCR detection
    GET    /api/jobs/{id}/frame        sampled preview frame (?index=N)
    POST   /api/jobs/{id}/regions      save user-adjusted regions
    POST   /api/jobs/{id}/process      {engine, regions?}
    GET    /api/jobs/{id}/download     processed MP4
    GET    /api/jobs/{id}/original     original upload (before/after preview)
    DELETE /api/jobs/{id}              delete now, no waiting for retention
"""
from __future__ import annotations

import json
import mimetypes
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import config, processing, storage
from .detection import probe_video

app = FastAPI(title="CLEANFRAME AI", version="1.0.0",
              description="Remove video captions. Keep everything else.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.FRONTEND_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.on_event("startup")
def _startup() -> None:
    storage.cleanup_expired()
    storage.start_cleanup_loop()


# ---------------------------------------------------------------- models


class RegionsPayload(BaseModel):
    regions: list[dict] = Field(default_factory=list)


class ProcessPayload(BaseModel):
    engine: str = "cpu"
    regions: list[dict] | None = None


# ---------------------------------------------------------------- helpers


def _require_job(job_id: str) -> dict:
    state = storage.load_state(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Job not found or expired")
    return state


def _validate_regions(regions: list[dict]) -> list[dict]:
    clean = []
    for r in regions:
        try:
            x, y = float(r["x"]), float(r["y"])
            w, h = float(r["w"]), float(r["h"])
            start, end = float(r.get("start", 0)), float(r.get("end", 1e9))
        except (KeyError, TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid region format")
        if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 and 0 < h <= 1):
            raise HTTPException(status_code=400, detail="Region must be inside 0..1")
        if x + w > 1.001 or y + h > 1.001 or end <= start:
            raise HTTPException(status_code=400, detail="Invalid region bounds/time")
        # Safety cap: a "caption region" may not cover most of the frame.
        # This is what stops the tool becoming a general object remover.
        if w * h > 0.6:
            raise HTTPException(
                status_code=400,
                detail="Region is too large for a caption area (max 60% of frame)")
        clean.append({"x": x, "y": y, "w": w, "h": h, "start": start, "end": end})
    return clean


def _public_state(state: dict) -> dict:
    return {k: state.get(k) for k in
            ("job_id", "status", "progress", "stage", "created_at", "filename",
             "video", "detection", "regions", "engine", "error", "error_code",
             "output_size", "output_video", "stats")}


# ---------------------------------------------------------------- routes


@app.get("/api/health")
def health():
    from .detection import pick_engine

    return {
        "status": "ok",
        "ocr_engine": pick_engine(),
        "propainter_configured": config.propainter_configured(),
        "default_engine": config.DEFAULT_ENGINE,
        "max_upload_mb": config.MAX_UPLOAD_MB,
        "retention_hours": config.RETENTION_HOURS,
        "allowed_formats": sorted(config.ALLOWED_EXTENSIONS),
    }


@app.post("/api/jobs/upload")
async def upload(video: UploadFile = File(...)):
    filename = Path(video.filename or "video").name
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Only {', '.join(sorted(config.ALLOWED_EXTENSIONS))} are supported")
    job_id = storage.new_job_id()
    d = storage.ensure_job_dir(job_id)
    input_path = d / f"input.{ext}"
    size = 0
    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    with input_path.open("wb") as fh:
        while True:
            chunk = await video.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                storage.delete_job(job_id)
                raise HTTPException(
                    status_code=413, detail=f"File exceeds {config.MAX_UPLOAD_MB} MB")
            fh.write(chunk)
    try:
        info = probe_video(input_path)
    except Exception:
        storage.delete_job(job_id)
        raise HTTPException(status_code=400, detail="Could not read video metadata")
    if not info.get("width") or not info.get("height"):
        storage.delete_job(job_id)
        raise HTTPException(status_code=400,
                            detail="No video stream found in this file")
    state = {
        "job_id": job_id, "status": "uploaded", "progress": 0,
        "stage": "Uploaded", "filename": filename, "size": size,
        "input_path": str(input_path), "video": info,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    storage.save_state(job_id, state)
    return _public_state(state)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    return _public_state(_require_job(job_id))


@app.post("/api/jobs/{job_id}/detect")
def detect(job_id: str, background: BackgroundTasks):
    state = _require_job(job_id)
    if state["status"] in ("detecting", "processing"):
        return _public_state(state)
    storage.update_state(job_id, status="detecting", progress=0,
                         stage="Detecting captions with OCR")
    background.add_task(_detect_task, job_id)
    return _public_state(storage.load_state(job_id) or state)


def _detect_task(job_id: str) -> None:
    try:
        processing.run_detection(job_id)
    except Exception as exc:  # noqa: BLE001
        storage.update_state(job_id, status="error", stage="Detection failed",
                             error=str(exc))


@app.get("/api/jobs/{job_id}/frame")
def frame(job_id: str, index: int = 0):
    state = _require_job(job_id)
    frames = (state.get("detection") or {}).get("preview_frames", [])
    if not frames or index < 0 or index >= len(frames):
        raise HTTPException(status_code=404, detail="Frame not found")
    path = storage.job_dir(job_id) / "frames" / frames[index]["file"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Frame file missing")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/jobs/{job_id}/detections")
def detections(job_id: str):
    state = _require_job(job_id)
    return {"detections": state.get("detections", []),
            "regions": state.get("regions", [])}


@app.post("/api/jobs/{job_id}/regions")
def save_regions(job_id: str, payload: RegionsPayload):
    _require_job(job_id)
    regions = _validate_regions(payload.regions)
    storage.update_state(job_id, regions=regions, status="review")
    return {"regions": regions}


@app.post("/api/jobs/{job_id}/process")
def process(job_id: str, payload: ProcessPayload, background: BackgroundTasks):
    state = _require_job(job_id)
    if state["status"] in ("detecting", "processing"):
        return _public_state(state)
    engine = payload.engine if payload.engine in ("cpu", "propainter") else "cpu"
    regions = (_validate_regions(payload.regions) if payload.regions is not None
               else state.get("regions") or [])
    if not regions:
        raise HTTPException(
            status_code=400,
            detail="No caption regions selected. Review detection or draw a region first.")
    if engine == "propainter" and not config.propainter_configured():
        raise HTTPException(
            status_code=503,
            detail=("ProPainter GPU is not configured on this server. "
                    "Use the CPU engine, or connect a GPU (see GPU.md)."))
    storage.update_state(job_id, status="processing", progress=0,
                         stage="Starting", engine=engine, regions=regions)
    background.add_task(_process_task, job_id, engine, regions)
    return _public_state(storage.load_state(job_id) or state)


def _process_task(job_id: str, engine: str, regions: list[dict]) -> None:
    try:
        processing.run_processing(job_id, engine, regions)
    except Exception:
        pass  # error state already recorded in run_processing


@app.get("/api/jobs/{job_id}/download")
def download(job_id: str):
    state = _require_job(job_id)
    output = storage.job_dir(job_id) / "output.mp4"
    if state.get("status") != "done" or not output.exists():
        raise HTTPException(status_code=409, detail="Processed video is not ready")
    return FileResponse(output, media_type="video/mp4",
                        filename="cleanframe-output.mp4")


@app.get("/api/jobs/{job_id}/original")
def original(job_id: str):
    state = _require_job(job_id)
    path = Path(state["input_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Original file missing")
    mime, _ = mimetypes.guess_type(str(path))
    return FileResponse(path, media_type=mime or "video/mp4")


@app.delete("/api/jobs/{job_id}")
def delete(job_id: str):
    if storage.delete_job(job_id):
        return {"deleted": True}
    raise HTTPException(status_code=404, detail="Job not found")


@app.get("/")
def root():
    return {"name": "CLEANFRAME AI", "api": "/api/health",
            "docs": "/docs"}
