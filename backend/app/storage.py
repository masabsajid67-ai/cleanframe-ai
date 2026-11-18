"""Temporary, per-job storage + automatic retention cleanup.

Layout:
    storage/jobs/<job_id>/input.<ext>     original upload (never served publicly)
    storage/jobs/<job_id>/output.mp4     processed video
    storage/jobs/<job_id>/frames/        sampled preview frames (OCR review)
    storage/jobs/<job_id>/job.json       job state (status, progress, regions)

Every job directory is deleted whole when it expires, when the user
deletes the job, or when processing is replaced. Nothing is kept
indefinitely and nothing leaves this directory except through the
authenticated-by-obscurity job download endpoint (random UUID ids).
"""
import json
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import config

_lock = threading.Lock()


def new_job_id() -> str:
    return uuid.uuid4().hex


def job_dir(job_id: str) -> Path:
    # Reject path traversal: job ids are hex only.
    if not job_id or any(c not in "0123456789abcdef" for c in job_id):
        raise ValueError("invalid job id")
    return config.STORAGE_DIR / "jobs" / job_id


def ensure_job_dir(job_id: str) -> Path:
    d = job_dir(job_id)
    (d / "frames").mkdir(parents=True, exist_ok=True)
    return d


def save_state(job_id: str, state: dict) -> None:
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    path = job_dir(job_id) / "job.json"
    with _lock:
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def load_state(job_id: str) -> dict | None:
    path = job_dir(job_id) / "job.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def update_state(job_id: str, **patch) -> dict | None:
    state = load_state(job_id) or {}
    state.update(patch)
    save_state(job_id, state)
    return state


def delete_job(job_id: str) -> bool:
    d = job_dir(job_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
        return True
    return False


def job_age_hours(job_id: str) -> float:
    state = load_state(job_id) or {}
    created = state.get("created_at")
    if not created:
        return 0.0
    try:
        dt = datetime.fromisoformat(created)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    except ValueError:
        return 0.0


def cleanup_expired() -> list[str]:
    """Delete every job older than RETENTION_HOURS. Returns deleted ids."""
    jobs_root = config.STORAGE_DIR / "jobs"
    if not jobs_root.exists():
        return []
    deleted = []
    for child in jobs_root.iterdir():
        if not child.is_dir():
            continue
        if job_age_hours(child.name) > config.RETENTION_HOURS:
            shutil.rmtree(child, ignore_errors=True)
            deleted.append(child.name)
    return deleted


def start_cleanup_loop() -> None:
    def _loop() -> None:
        while True:
            time.sleep(config.CLEANUP_INTERVAL_SECONDS)
            try:
                cleanup_expired()
            except Exception:
                pass  # cleanup must never crash the server

    thread = threading.Thread(target=_loop, daemon=True, name="retention-cleanup")
    thread.start()
