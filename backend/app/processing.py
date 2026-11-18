"""Job pipeline: detect -> (user reviews regions) -> inpaint -> mux audio.

Guarantees from the spec, enforced here:
- Original resolution / fps are preserved (no crop, no zoom, no resize).
- Original audio is copied back with ffmpeg (`-c:a copy`) when present.
- Only approved caption regions are inpainted; everything else is
  passed through untouched by the mask logic in inpaint.py.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import config, storage
from .detection import detect_captions, probe_video
from .inpaint import inpaint_cpu, inpaint_propainter, PropainterNotConfigured


def mux_audio(silent_video: Path, original: Path, output: Path, has_audio: bool) -> None:
    """Re-encode video (H.264, same size/fps) and copy the original audio."""
    if has_audio:
        cmd = ["ffmpeg", "-y", "-i", str(silent_video), "-i", str(original),
               "-map", "0:v:0", "-map", "1:a:0",
               "-c:v", "libx264", "-crf", str(config.VIDEO_CRF),
               "-pix_fmt", "yuv420p", "-c:a", "copy",
               "-shortest", str(output)]
    else:
        cmd = ["ffmpeg", "-y", "-i", str(silent_video),
               "-c:v", "libx264", "-crf", str(config.VIDEO_CRF),
               "-pix_fmt", "yuv420p", str(output)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if proc.returncode != 0 or not output.exists():
        raise RuntimeError(f"ffmpeg mux failed: {proc.stderr[-800:]}")


def run_detection(job_id: str) -> dict:
    state = storage.load_state(job_id) or {}
    d = storage.job_dir(job_id)
    input_path = Path(state["input_path"])
    frames_dir = d / "frames"
    frames_dir.mkdir(exist_ok=True)

    def _progress(pct: int) -> None:
        storage.update_state(job_id, status="detecting", progress=pct,
                             stage="Detecting captions with OCR")

    result = detect_captions(input_path, frames_dir, on_progress=_progress)
    storage.update_state(
        job_id, status="review", progress=100, stage="Review detected areas",
        detection={k: result[k] for k in
                   ("engine", "regions", "preview_frames", "total_boxes",
                    "avg_confidence", "needs_review", "review_reason")},
        detections=result["detections"], video=result["video"],
        regions=result["regions"])
    return result


def run_processing(job_id: str, engine: str, regions: list[dict]) -> dict:
    state = storage.load_state(job_id) or {}
    d = storage.job_dir(job_id)
    input_path = Path(state["input_path"])
    silent = d / "silent.mp4"
    output = d / "output.mp4"
    storage.update_state(job_id, status="processing", progress=0,
                         stage="Removing captions", engine=engine,
                         regions=regions, error=None)

    def _progress(pct: int) -> None:
        # Inpainting is 0..90, mux is 90..100.
        storage.update_state(job_id, progress=int(pct * 0.9),
                             stage="Reconstructing background behind captions")

    try:
        if engine == "propainter":
            stats = inpaint_propainter(input_path, regions, silent, _progress)
        else:
            stats = inpaint_cpu(input_path, regions, silent, _progress)
        storage.update_state(job_id, progress=92, stage="Restoring original audio")
        info = probe_video(input_path)
        mux_audio(silent, input_path, output, info.get("has_audio", False))
        out_info = probe_video(output)
        silent.unlink(missing_ok=True)
        storage.update_state(job_id, status="done", progress=100,
                             stage="Done", output_size=output.stat().st_size,
                             output_video=out_info, stats=stats)
        return {"status": "done", "stats": stats, "output_video": out_info}
    except PropainterNotConfigured as exc:
        storage.update_state(job_id, status="error", stage="GPU not configured",
                             error=str(exc), error_code="PROPINTER_NOT_CONFIGURED")
        raise
    except Exception as exc:  # noqa: BLE001 - surface real errors to the UI
        storage.update_state(job_id, status="error", stage="Processing failed",
                             error=str(exc))
        raise
