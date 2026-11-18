"""Generate a small test video with burned-in captions + a tone audio track.

Usage:  python3 scripts/make_sample_video.py [output.mp4]
Requires: ffmpeg on PATH. No fonts beyond DejaVu Sans (ships with ffmpeg
drawtext on most Linux systems; falls back to a plain colour video if
drawtext is unavailable — detection will then find no text, which is
itself a valid test of the review flow).
"""
import subprocess
import sys
from pathlib import Path

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("sample_captioned.mp4")

FILTER = (
    "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
    "text='HELLO WORLD CAPTION':fontsize=44:fontcolor=white:borderw=2:bordercolor=black:"
    "x=(w-text_w)/2:y=h-90,"
    "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
    "text='Second line of subtitles here':fontsize=36:fontcolor=yellow:borderw=2:bordercolor=black:"
    "x=(w-text_w)/2:y=h-150"
)

cmd = [
    "ffmpeg", "-y",
    "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=6",
    "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
    "-vf", FILTER,
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
    str(OUT),
]
proc = subprocess.run(cmd, capture_output=True, text=True)
if proc.returncode != 0:
    print("drawtext failed, making plain video instead:")
    print(proc.stderr[-500:])
    cmd2 = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=6",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
        str(OUT),
    ]
    subprocess.run(cmd2, check=True)
print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")
