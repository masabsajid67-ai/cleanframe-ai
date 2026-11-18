"""ProPainter GPU worker — RunPod serverless handler (also Modal-adaptable).

Contract with the CLEANFRAME backend (backend/app/inpaint.py):
    input:  {"video_b64": "<mp4 bytes, base64>", "regions": [{x,y,w,h,start,end}, ...]}
    output: {"video_b64": "<inpainted mp4 bytes, base64, SILENT — audio is
             re-attached by the backend so the original track is preserved>"}

Only the caption regions are masked. The mask video is rendered from the
regions with the same fps/size as the input, then ProPainter inpaints it.
This worker runs ONLY on a GPU machine / RunPod endpoint — it is never
imported by the CPU backend.

Deploy (RunPod): build gpu/Dockerfile.gpu, push the image, create a
Serverless endpoint with an RTX 3090/4090 (24 GB), workers min 0.
See GPU.md for step-by-step + costs.
"""
import base64
import os
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np

PROPINTER_DIR = os.environ.get("PROPINTER_DIR", "/opt/ProPainter")


def render_mask_video(video_path: Path, regions: list, out_path: Path) -> None:
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"),
                             fps, (width, height), isColor=False)
    idx = 0
    while True:
        ok, _ = cap.read()
        if not ok:
            break
        t = idx / fps if fps else 0.0
        mask = np.zeros((height, width), dtype=np.uint8)
        for r in regions:
            if float(r.get("start", 0)) <= t <= float(r.get("end", 1e9)):
                x = max(0, int(float(r["x"]) * width) - 4)
                y = max(0, int(float(r["y"]) * height) - 4)
                x2 = min(width, int((float(r["x"]) + float(r["w"])) * width) + 4)
                y2 = min(height, int((float(r["y"]) + float(r["h"])) * height) + 4)
                cv2.rectangle(mask, (x, y), (x2, y2), 255, thickness=cv2.FILLED)
        writer.write(mask)
        idx += 1
    writer.release()
    cap.release()


def run_propainter(video_path: Path, mask_path: Path, out_path: Path) -> None:
    cmd = ["python3", "inference_propainter.py",
           "--video", str(video_path), "--mask", str(mask_path),
           "--output", str(out_path), "--resize_ratio", "1.0"]
    proc = subprocess.run(cmd, cwd=PROPINTER_DIR, capture_output=True,
                          text=True, timeout=3600)
    if proc.returncode != 0 or not out_path.exists():
        raise RuntimeError(f"ProPainter failed: {proc.stderr[-1000:]}")


def handler(job: dict) -> dict:
    payload = job.get("input", {})
    video_b64 = payload["video_b64"]
    regions = payload.get("regions", [])
    if not regions:
        raise ValueError("No caption regions supplied — refusing to process")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        video_path = tmp / "input.mp4"
        video_path.write_bytes(base64.b64decode(video_b64))
        mask_path = tmp / "masks.mp4"
        out_path = tmp / "inpainted.mp4"
        render_mask_video(video_path, regions, mask_path)
        run_propainter(video_path, mask_path, out_path)
        return {"video_b64": base64.b64encode(out_path.read_bytes()).decode()}


if __name__ == "__main__":
    # RunPod entrypoint. `runpod` is installed only in the GPU image.
    import runpod

    runpod.serverless.start({"handler": handler})
