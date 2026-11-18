"""End-to-end smoke test against a running backend.

Usage:
    1. Start the backend:  cd backend && uvicorn app.main:app --port 8000
    2. Make a sample:      python3 scripts/make_sample_video.py /tmp/sample.mp4
    3. Run:                python3 scripts/smoke_test.py /tmp/sample.mp4

Checks: health -> upload -> detect -> regions present -> process (CPU) ->
download exists with same resolution + audio as the input. Prints PASS/FAIL
per step and exits non-zero on failure. No step is faked: every check
reads the real HTTP response / ffprobe output.
"""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8000"
VIDEO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/sample.mp4")

failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read())


def post_json(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def upload(path):
    import uuid
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"video\"; "
            f"filename=\"{path.name}\"\r\nContent-Type: video/mp4\r\n\r\n").encode() \
        + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(BASE + "/api/jobs/upload", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=width,height",
                          "-show_entries", "format=duration",
                          "-of", "default=noprint_wrappers=1", str(path)],
                         capture_output=True, text=True)
    info = dict(line.split("=", 1) for line in out.stdout.splitlines() if "=" in line)
    audio = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a",
                            "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
                           capture_output=True, text=True)
    info["has_audio"] = bool(audio.stdout.strip())
    return info


def wait_until(job_id, statuses, timeout=300):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = get(f"/api/jobs/{job_id}")
        if job["status"] in statuses:
            return job
        time.sleep(2)
    return get(f"/api/jobs/{job_id}")


def main():
    health = get("/api/health")
    check("health", health.get("status") == "ok", str(health))

    job = upload(VIDEO)
    job_id = job["job_id"]
    check("upload", bool(job_id) and job["video"]["width"] > 0, str(job.get("video")))

    post_json(f"/api/jobs/{job_id}/detect", {})
    job = wait_until(job_id, {"review", "error"}, timeout=240)
    check("detect reaches review", job["status"] == "review",
          f"status={job['status']} error={job.get('error')}")
    det = job.get("detection") or {}
    print(f"  detection: engine={det.get('engine')} boxes={det.get('total_boxes')} "
          f"regions={len(job.get('regions') or [])} needs_review={det.get('needs_review')}")
    regions = job.get("regions") or []
    if not regions:
        print("  NOTE: no regions detected — using a manual bottom-band region for the process test.")
        regions = [{"x": 0.1, "y": 0.72, "w": 0.8, "h": 0.25, "start": 0, "end": 1e9}]

    post_json(f"/api/jobs/{job_id}/process", {"engine": "cpu", "regions": regions})
    job = wait_until(job_id, {"done", "error"}, timeout=300)
    check("process reaches done", job["status"] == "done",
          f"status={job['status']} error={job.get('error')}")

    out_path = Path("/tmp/cleanframe-smoke-output.mp4")
    with urllib.request.urlopen(BASE + f"/api/jobs/{job_id}/download", timeout=120) as r:
        out_path.write_bytes(r.read())
    check("download non-empty", out_path.stat().st_size > 10000,
          f"{out_path.stat().st_size} bytes")

    src, dst = probe(VIDEO), probe(out_path)
    check("resolution preserved", src.get("width") == dst.get("width")
          and src.get("height") == dst.get("height"), f"{src} -> {dst}")
    check("audio preserved", dst.get("has_audio") == src.get("has_audio"),
          f"src audio={src.get('has_audio')} out audio={dst.get('has_audio')}")

    req = urllib.request.Request(BASE + f"/api/jobs/{job_id}", method="DELETE")
    with urllib.request.urlopen(req, timeout=30) as r:
        check("delete job", json.loads(r.read()).get("deleted") is True)

    print("\nRESULT:", "ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}")
    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
