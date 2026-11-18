"""Caption / subtitle detection with OCR.

Pipeline
--------
1. Sample frames at DETECT_FPS (default 1 fps, capped) with OpenCV.
2. Run the best available OCR engine (RapidOCR -> EasyOCR -> Tesseract).
3. Convert every detection to a normalised box {x, y, w, h} in 0..1,
   merged per frame so overlapping words become one caption box.
4. Cluster boxes across time into "suggested regions" the user can
   review and edit before any pixel is removed.

Safety rule: detection NEVER removes anything. It only proposes boxes.
Removal happens only in processing.py, only inside approved boxes, so
faces, logos, people and scenery outside a caption box are untouched.

If no OCR engine is installed, detection returns engine="none" and
needs_review=True so the frontend asks the user to draw regions
manually instead of pretending text was found.
"""
from __future__ import annotations

import subprocess
import math
from pathlib import Path

import cv2
import numpy as np

from . import config

# ---------------------------------------------------------------- OCR engines


def _rapidocr_boxes(frame_bgr):
    from rapidocr_onnxruntime import RapidOCR  # lazy: heavy import

    engine = _rapidocr_boxes.engine  # type: ignore[attr-defined]
    if engine is None:
        engine = RapidOCR()
        _rapidocr_boxes.engine = engine  # type: ignore[attr-defined]
    result, _ = engine(frame_bgr)
    boxes = []
    if not result:
        return boxes
    for poly, text, conf in result:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        boxes.append({"poly": poly, "text": str(text), "confidence": float(conf),
                      "x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys)})
    return boxes


_rapidocr_boxes.engine = None  # type: ignore[attr-defined]


def _easyocr_boxes(frame_bgr, reader):
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    results = reader.readtext(rgb)
    boxes = []
    for poly, text, conf in results:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        boxes.append({"poly": poly, "text": str(text), "confidence": float(conf),
                      "x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys)})
    return boxes


def _tesseract_boxes(frame_bgr):
    import pytesseract

    data = pytesseract.image_to_data(frame_bgr, output_type=pytesseract.Output.DICT)
    boxes = []
    n = len(data.get("text", []))
    for i in range(n):
        text = (data["text"][i] or "").strip()
        if not text:
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            continue
        if conf < 0:
            continue
        x, y = int(data["left"][i]), int(data["top"][i])
        w, h = int(data["width"][i]), int(data["height"][i])
        if w <= 0 or h <= 0:
            continue
        boxes.append({"text": text, "confidence": conf / 100.0,
                      "x0": x, "y0": y, "x1": x + w, "y1": y + h})
    return boxes


def pick_engine() -> str:
    """Return the first usable engine name, honouring OCR_ENGINE=auto order."""
    wanted = config.OCR_ENGINE.lower()
    order = ["rapidocr", "easyocr", "tesseract"] if wanted == "auto" else [wanted]
    for name in order:
        try:
            if name == "rapidocr":
                import rapidocr_onnxruntime  # noqa: F401
                return "rapidocr"
            if name == "easyocr":
                import easyocr  # noqa: F401
                return "easyocr"
            if name == "tesseract":
                import pytesseract  # noqa: F401
                if shutil_which("tesseract"):
                    return "tesseract"
        except ImportError:
            continue
    return "none"


def shutil_which(cmd: str) -> str | None:
    import shutil

    return shutil.which(cmd)


# ---------------------------------------------------------------- geometry


def _merge_overlapping(boxes, w, h, gap_px=12):
    """Merge boxes that overlap or nearly touch on the same line."""
    if not boxes:
        return []
    rects = sorted(boxes, key=lambda b: (b["y0"], b["x0"]))
    merged = []
    for b in rects:
        placed = False
        for m in merged:
            same_line = abs(b["y0"] - m["y0"]) < max(20, (b["y1"] - b["y0"]))
            near = (b["x0"] <= m["x1"] + gap_px and m["x0"] <= b["x1"] + gap_px
                    and b["y0"] <= m["y1"] + gap_px and m["y0"] <= b["y1"] + gap_px)
            if same_line and near:
                m["x0"] = min(m["x0"], b["x0"])
                m["y0"] = min(m["y0"], b["y0"])
                m["x1"] = max(m["x1"], b["x1"])
                m["y1"] = max(m["y1"], b["y1"])
                m["text"] = (m["text"] + " " + b["text"]).strip()
                m["confidence"] = max(m["confidence"], b["confidence"])
                placed = True
                break
        if not placed:
            merged.append(dict(b))
    out = []
    for m in merged:
        bw, bh = m["x1"] - m["x0"], m["y1"] - m["y0"]
        if bw < 8 or bh < 6:  # noise
            continue
        out.append({
            "x": round(m["x0"] / w, 4), "y": round(m["y0"] / h, 4),
            "w": round(bw / w, 4), "h": round(bh / h, 4),
            "text": m["text"][:120], "confidence": round(m["confidence"], 3),
        })
    return out


def cluster_regions(detections):
    """Group per-frame boxes into stable caption regions over time.

    Boxes whose vertical centres are within 8% of frame height and whose
    horizontal ranges overlap are treated as one caption band. Each
    region gets the union box and a [start, end] time range.
    """
    regions = []
    for det in detections:
        t = det["time"]
        for box in det["boxes"]:
            cy = box["y"] + box["h"] / 2
            matched = None
            for r in regions:
                rcy = r["y"] + r["h"] / 2
                h_overlap = not (box["x"] > r["x"] + r["w"] or r["x"] > box["x"] + box["w"])
                if abs(cy - rcy) < 0.08 and h_overlap and t - r["end"] <= 2.0:
                    matched = r
                    break
            if matched is None:
                regions.append({**box, "start": t, "end": t, "count": 1,
                                "texts": [box["text"]] if box["text"] else []})
            else:
                x0 = min(matched["x"], box["x"])
                y0 = min(matched["y"], box["y"])
                x1 = max(matched["x"] + matched["w"], box["x"] + box["w"])
                y1 = max(matched["y"] + matched["h"], box["y"] + box["h"])
                matched.update({"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0,
                                "end": t, "count": matched["count"] + 1})
                if box["text"] and box["text"] not in matched["texts"]:
                    matched["texts"].append(box["text"])
    for r in regions:
        r["confidence"] = round(
            sum(d["confidence"] for d in [b for det in detections for b in det["boxes"]]) / max(1, sum(len(det["boxes"]) for det in detections)), 3
        ) if detections else 0.0
        r.pop("text", None)
    return regions


# ---------------------------------------------------------------- video probe


def probe_video(path: Path) -> dict:
    """ffprobe metadata: resolution, fps, duration, audio presence."""
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
           "-show_entries", "stream=width,height,r_frame_rate,codec_name",
           "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1", str(path)]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    info = {"width": 0, "height": 0, "fps": 0.0, "duration": 0.0, "codec": ""}
    for line in out.stdout.splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k == "width":
            info["width"] = int(v)
        elif k == "height":
            info["height"] = int(v)
        elif k == "r_frame_rate" and "/" in v:
            num, den = v.split("/")
            info["fps"] = float(num) / float(den) if float(den) else 0.0
        elif k == "duration":
            info["duration"] = float(v)
        elif k == "codec_name":
            info["codec"] = v
    audio = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=index", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, timeout=30)
    info["has_audio"] = bool(audio.stdout.strip())
    return info


# ---------------------------------------------------------------- main entry


def detect_captions(video_path: Path, frames_dir: Path, on_progress=None) -> dict:
    """Run OCR over sampled frames. Returns detections + preview metadata."""
    info = probe_video(video_path)
    engine = pick_engine()
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError("Could not open video for detection")
    fps = cap.get(cv2.CAP_PROP_FPS) or info.get("fps") or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or info.get("width") or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or info.get("height") or 0)
    duration = total_frames / fps if fps else info.get("duration", 0.0)

    step = max(1, int(round(fps / max(config.DETECT_FPS, 0.1))))
    sample_idx = list(range(0, total_frames, step))[: config.MAX_DETECT_FRAMES]
    if not sample_idx:
        sample_idx = [0]

    easy_reader = None
    if engine == "easyocr":
        import easyocr

        easy_reader = easyocr.Reader(["en"], gpu=False, verbose=False)

    detections = []
    preview_frames = []
    for n, idx in enumerate(sample_idx):
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        t = idx / fps if fps else 0.0
        frame_path = frames_dir / f"frame_{n:03d}.jpg"
        cv2.imwrite(str(frame_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
        preview_frames.append({"index": n, "time": round(t, 2),
                               "file": frame_path.name})
        if engine == "none":
            boxes = []
        elif engine == "rapidocr":
            raw = _rapidocr_boxes(frame)
            raw = [b for b in raw if b["confidence"] >= config.OCR_MIN_CONFIDENCE]
            boxes = _merge_overlapping(raw, width, height)
        elif engine == "easyocr":
            raw = _easyocr_boxes(frame, easy_reader)
            raw = [b for b in raw if b["confidence"] >= config.OCR_MIN_CONFIDENCE]
            boxes = _merge_overlapping(raw, width, height)
        else:
            raw = _tesseract_boxes(frame)
            raw = [b for b in raw if b["confidence"] >= config.OCR_MIN_CONFIDENCE]
            boxes = _merge_overlapping(raw, width, height)
        detections.append({"index": n, "time": round(t, 2), "boxes": boxes})
        if on_progress:
            on_progress(int((n + 1) / len(sample_idx) * 100))
    cap.release()

    all_boxes = [b for d in detections for b in d["boxes"]]
    avg_conf = (sum(b["confidence"] for b in all_boxes) / len(all_boxes)) if all_boxes else 0.0
    regions = cluster_regions(detections)
    needs_review = bool(
        engine == "none" or not all_boxes or avg_conf < config.REVIEW_CONFIDENCE
    )
    return {
        "engine": engine,
        "video": {**info, "width": width, "height": height, "fps": round(fps, 3),
                  "duration": round(duration, 2)},
        "detections": detections,
        "regions": regions,
        "preview_frames": preview_frames,
        "total_boxes": len(all_boxes),
        "avg_confidence": round(avg_conf, 3),
        "needs_review": needs_review,
        "review_reason": (
            "No OCR engine is installed — draw caption regions manually."
            if engine == "none" else
            "No text was detected — check the frames and draw regions if captions exist."
            if not all_boxes else
            "Detection confidence is low — please review the detected areas before processing."
            if avg_conf < config.REVIEW_CONFIDENCE else ""
        ),
    }
