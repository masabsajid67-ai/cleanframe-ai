"""CLEANFRAME AI — configuration from environment only.

No secret is ever read from, or written to, frontend code. GPU keys live
here, server-side, in environment variables.
"""
import os
from pathlib import Path


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = Path(os.environ.get("CLEANFRAME_STORAGE_DIR", BASE_DIR / "storage"))
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# Upload limits
MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", 500)
ALLOWED_EXTENSIONS = {"mp4", "mov", "webm"}
ALLOWED_MIME_PREFIXES = ("video/",)

# Retention: uploaded + processed files are deleted automatically.
RETENTION_HOURS = _float("RETENTION_HOURS", 24.0)
CLEANUP_INTERVAL_SECONDS = _int("CLEANUP_INTERVAL_SECONDS", 600)

# OCR detection
DETECT_FPS = _float("DETECT_FPS", 1.0)  # frames sampled per second for OCR
MAX_DETECT_FRAMES = _int("MAX_DETECT_FRAMES", 90)
OCR_MIN_CONFIDENCE = _float("OCR_MIN_CONFIDENCE", 0.45)
REVIEW_CONFIDENCE = _float("REVIEW_CONFIDENCE", 0.65)  # below -> ask user to review
OCR_ENGINE = os.environ.get("OCR_ENGINE", "auto")  # auto | rapidocr | easyocr | tesseract

# Inpainting
INPAINT_PAD_PX = _int("INPAINT_PAD_PX", 4)  # dilation around each detected box
INPAINT_RADIUS = _int("INPAINT_RADIUS", 3)
VIDEO_CRF = _int("VIDEO_CRF", 18)  # quality of the re-encode (lower = better)
DEFAULT_ENGINE = os.environ.get("DEFAULT_ENGINE", "cpu")  # cpu | propainter

# ProPainter GPU (optional, server-side only). When unset, the GPU engine
# reports PROPINTER_NOT_CONFIGURED instead of faking a result.
PROPINTER_MODE = os.environ.get("PROPINTER_MODE", "runpod")  # runpod | http | local
RUNPOD_ENDPOINT_ID = os.environ.get("RUNPOD_ENDPOINT_ID", "")
RUNPOD_API_KEY = os.environ.get("RUNPOD_API_KEY", "")
PROPINTER_ENDPOINT_URL = os.environ.get("PROPINTER_ENDPOINT_URL", "")
PROPINTER_API_KEY = os.environ.get("PROPINTER_API_KEY", "")
PROPINTER_TIMEOUT_SECONDS = _int("PROPINTER_TIMEOUT_SECONDS", 1800)
PROPINTER_LOCAL_DIR = os.environ.get("PROPINTER_LOCAL_DIR", "")

# CORS: comma-separated origins allowed to call this API.
FRONTEND_ORIGINS = [
    o.strip() for o in os.environ.get(
        "FRONTEND_ORIGINS", "http://localhost:5173,http://localhost:3000"
    ).split(",") if o.strip()
]

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = _int("PORT", 8000)


def propainter_configured() -> bool:
    if PROPINTER_MODE == "runpod":
        return bool(RUNPOD_ENDPOINT_ID and RUNPOD_API_KEY)
    if PROPINTER_MODE == "http":
        return bool(PROPINTER_ENDPOINT_URL)
    if PROPINTER_MODE == "local":
        return bool(PROPINTER_LOCAL_DIR and Path(PROPINTER_LOCAL_DIR).exists())
    return False
