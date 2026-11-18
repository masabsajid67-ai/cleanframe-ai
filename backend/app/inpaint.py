"""Video inpainting engines.

Two engines, one contract: given an input video and a list of caption
regions (normalised boxes with time ranges), produce a video where ONLY
those boxes are reconstructed. Resolution, frame rate and audio are
preserved by the mux step in processing.py.

1. CPU engine (default, free, no GPU): OpenCV Telea inpainting inside
   the caption mask only. Best on plain / slowly moving backgrounds
   (the common subtitle case). Honest about its limits: fast-moving,
   detailed backgrounds behind text will look softer than ProPainter.
2. ProPainter engine (GPU): delegates to a RunPod serverless endpoint,
   a generic HTTP GPU worker, or a local ProPainter checkout. If the
   GPU is not configured it FAILS with PROPINTER_NOT_CONFIGURED —
   it never silently falls back and never fakes a result.
"""
from __future__ import annotations

import base64
import json
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np

from . import config


# ---------------------------------------------------------------- masks


def boxes_at_time(regions: list[dict], t: float) -> list[dict]:
    return [r for r in regions if r.get("start", 0) <= t <= r.get("end", 1e9)]


def build_mask(width: int, height: int, boxes: list[dict], pad_px: int) -> np.ndarray:
    """White mask ONLY inside caption boxes, black everywhere else."""
    mask = np.zeros((height, width), dtype=np.uint8)
    for b in boxes:
        x = max(0, int(b["x"] * width) - pad_px)
        y = max(0, int(b["y"] * height) - pad_px)
        x2 = min(width, int((b["x"] + b["w"]) * width) + pad_px)
        y2 = min(height, int((b["y"] + b["h"]) * height) + pad_px)
        if x2 > x and y2 > y:
            cv2.rectangle(mask, (x, y), (x2, y2), 255, thickness=cv2.FILLED)
    return mask


# ---------------------------------------------------------------- CPU engine


def inpaint_cpu(input_path: Path, regions: list[dict], silent_output: Path,
                on_progress=None) -> dict:
    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise RuntimeError("Could not open video for inpainting")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(silent_output), fourcc, fps, (width, height))
    if not writer.isOpened():
        cap.release()
        raise RuntimeError("Could not create output video writer")

    frames_done = 0
    frames_masked = 0
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        t = idx / fps if fps else 0.0
        boxes = boxes_at_time(regions, t)
        if boxes:
            mask = build_mask(width, height, boxes, config.INPAINT_PAD_PX)
            if np.any(mask):
                # Dilate slightly so text edges do not survive as a halo,
                # then inpaint ONLY the masked pixels.
                kernel = np.ones((3, 3), np.uint8)
                mask = cv2.dilate(mask, kernel, iterations=1)
                frame = cv2.inpaint(frame, mask, config.INPAINT_RADIUS,
                                    cv2.INPAINT_TELEA)
                frames_masked += 1
        writer.write(frame)
        idx += 1
        frames_done += 1
        if on_progress and total:
            on_progress(int(frames_done / total * 100))
    writer.release()
    cap.release()
    return {"engine": "cpu-opencv-telea", "frames": frames_done,
            "frames_masked": frames_masked, "width": width, "height": height,
            "fps": round(fps, 3)}


# ---------------------------------------------------------------- ProPainter


class PropainterNotConfigured(RuntimeError):
    code = "PROPINTER_NOT_CONFIGURED"


def _runpod_call(video_b64: str, regions: list[dict], timeout: int) -> bytes:
    import urllib.request

    api = f"https://api.runpod.ai/v2/{config.RUNPOD_ENDPOINT_ID}/run"
    payload = json.dumps({"input": {"video_b64": video_b64, "regions": regions}}).encode()
    req = urllib.request.Request(api, data=payload, headers={
        "Authorization": f"Bearer {config.RUNPOD_API_KEY}",
        "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        job = json.loads(resp.read())
    job_id = job["id"]
    status_url = f"https://api.runpod.ai/v2/{config.RUNPOD_ENDPOINT_ID}/status/{job_id}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        req = urllib.request.Request(status_url, headers={
            "Authorization": f"Bearer {config.RUNPOD_API_KEY}"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            status = json.loads(resp.read())
        state = status.get("status")
        if state == "COMPLETED":
            out_b64 = status["output"]["video_b64"]
            return base64.b64decode(out_b64)
        if state in ("FAILED", "CANCELLED", "TIMED_OUT"):
            raise RuntimeError(f"ProPainter job {state}: {status.get('error') or status}")
        time.sleep(5)
    raise TimeoutError("ProPainter job timed out")


def _http_call(video_bytes: bytes, regions: list[dict], timeout: int) -> bytes:
    import urllib.request

    payload = json.dumps({
        "video_b64": base64.b64encode(video_bytes).decode(),
        "regions": regions}).encode()
    headers = {"Content-Type": "application/json"}
    if config.PROPINTER_API_KEY:
        headers["Authorization"] = f"Bearer {config.PROPINTER_API_KEY}"
    req = urllib.request.Request(config.PROPINTER_ENDPOINT_URL, data=payload,
                                 headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    return base64.b64decode(data["video_b64"])


def inpaint_propainter(input_path: Path, regions: list[dict],
                       silent_output: Path, on_progress=None) -> dict:
    if not config.propainter_configured():
        raise PropainterNotConfigured(
            "ProPainter GPU is not configured. Set RUNPOD_ENDPOINT_ID + "
            "RUNPOD_API_KEY (or PROPINTER_ENDPOINT_URL) in the backend "
            "environment — see GPU.md. The free CPU engine still works.")
    if on_progress:
        on_progress(5)
    if config.PROPINTER_MODE == "local":
        return _inpaint_propainter_local(input_path, regions, silent_output, on_progress)
    video_bytes = input_path.read_bytes()
    if config.PROPINTER_MODE == "runpod":
        out = _runpod_call(base64.b64encode(video_bytes).decode(), regions,
                           config.PROPINTER_TIMEOUT_SECONDS)
    else:
        out = _http_call(video_bytes, regions, config.PROPINTER_TIMEOUT_SECONDS)
    silent_output.write_bytes(out)
    if on_progress:
        on_progress(100)
    return {"engine": "propainter-gpu", "frames": 0, "frames_masked": 0}


def _inpaint_propainter_local(input_path: Path, regions: list[dict],
                              silent_output: Path, on_progress=None) -> dict:
    """Run a local ProPainter checkout (GPU machine only).

    Expects PROPINTER_LOCAL_DIR to hold the official ProPainter repo
    (https://github.com/sczhou/ProPainter) with weights downloaded.
    Masks are rendered as a black/white video with the same fps/size.
    """
    repo = Path(config.PROPINTER_LOCAL_DIR)
    work = silent_output.parent / "propainter"
    work.mkdir(exist_ok=True)
    mask_video = work / "masks.mp4"
    cap = cv2.VideoCapture(str(input_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(str(mask_video), cv2.VideoWriter_fourcc(*"mp4v"),
                             fps, (width, height), isColor=False)
    idx = 0
    while True:
        ok, _ = cap.read()
        if not ok:
            break
        t = idx / fps if fps else 0.0
        writer.write(build_mask(width, height, boxes_at_time(regions, t),
                                config.INPAINT_PAD_PX))
        idx += 1
    writer.release()
    cap.release()
    cmd = ["python3", "inference_propainter.py",
           "--video", str(input_path), "--mask", str(mask_video),
           "--output", str(silent_output), "--resize_ratio", "1.0",
           "--save_frames", "False"]
    proc = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True,
                          timeout=config.PROPINTER_TIMEOUT_SECONDS)
    if proc.returncode != 0 or not silent_output.exists():
        raise RuntimeError(f"Local ProPainter failed: {proc.stderr[-800:]}")
    if on_progress:
        on_progress(100)
    return {"engine": "propainter-local", "frames": idx, "frames_masked": idx}
