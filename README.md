# CLEANFRAME AI

> **Remove Video Captions. Keep Everything Else.**
>
> Clean your videos with AI-powered caption removal.

CLEANFRAME AI does **one thing only**: remove burned-in captions and subtitles from videos. It never removes logos, people, objects or backgrounds, and it never crops or zooms to hide text. The background behind the caption is reconstructed frame by frame, and the original resolution, frame rate and audio are preserved.

## What is in this project

A real, working full-stack application — not a mockup. Every button in the frontend calls a real backend endpoint.

```
cleanframe-ai/
├── frontend/            React + Vite (black & white premium UI)
│   └── src/
│       ├── App.jsx              Home, Privacy, Terms, routing
│       ├── Workspace.jsx        Upload → Detect → Review → Process → Download
│       ├── api.js               Backend client (no API keys, ever)
│       └── components/RegionEditor.jsx   Drag / resize / draw caption areas
├── backend/             Python FastAPI + FFmpeg + OCR + OpenCV
│   └── app/
│       ├── main.py              REST API (upload, detect, regions, process, download)
│       ├── detection.py         OCR caption detection + suggested regions
│       ├── inpaint.py           CPU inpainting + ProPainter GPU adapter
│       ├── processing.py        Pipeline: inpaint → re-attach original audio
│       ├── storage.py           Temporary storage + automatic retention cleanup
│       └── config.py            All settings from environment variables
├── gpu/                 ProPainter worker (RunPod serverless) + GPU Dockerfile
├── scripts/             Sample-video generator + end-to-end smoke test
├── docker-compose.yml   One-command local / VPS deployment
├── DEPLOYMENT.md        Step-by-step deployment (free options first)
└── GPU.md               How to connect ProPainter, and what it costs
```

## How it works

1. **Upload** — MP4, MOV or WEBM, drag-and-drop, up to 500 MB (configurable).
2. **Detect** — Frames are sampled at 1 fps and OCR (RapidOCR by default, EasyOCR/Tesseract fallbacks) finds visible text. Detections are merged per frame and clustered into suggested caption regions over time.
3. **Review** — If detection is uncertain (low confidence, or no text found), the user is asked to review first. Regions can be moved, resized, redrawn, or given exact start/end times. Nothing is removed before this step.
4. **Process** — Only the approved regions are inpainted:
   - **CPU engine (free, included):** OpenCV Telea inpainting inside the mask only. Best on plain / slow-moving backgrounds.
   - **ProPainter engine (GPU, optional):** motion-aware AI video inpainting via RunPod / Modal / local GPU. See `GPU.md`.
5. **Compare & download** — Synchronised before/after player with a drag handle, then a downloadable MP4 with the original audio track copied back untouched.

## Safety rules enforced in code

- Masks are built **only** inside approved caption boxes (`backend/app/inpaint.py: build_mask`). Everything outside a box passes through untouched.
- A region may not cover more than 60% of the frame (`backend/app/main.py`), so the tool cannot become a general object/background remover.
- No cropping, no zooming, no resize: output resolution and fps match the input; verified by the smoke test.
- Uploaded and processed videos are deleted automatically after `RETENTION_HOURS` (default 24h), and immediately on user request.
- No API key exists anywhere in frontend code. GPU keys live only in backend environment variables.

## Honest limits (read before selling this)

- The **CPU engine is real but not magic**. On busy, fast-moving backgrounds behind text it will look softer than ProPainter. For commercial client work with complex footage, connect the GPU engine.
- **ProPainter needs an NVIDIA GPU** (24 GB VRAM recommended). It cannot run on Netlify, Vercel, or any free static host, and it cannot run on a phone. The backend must run on a VPS/pod or delegate to RunPod serverless. Costs are in `GPU.md` (~$0.05–$0.30 per short video on RunPod; Modal includes $30/month of free compute).
- OCR can miss stylised, tiny, or partially transparent text. That is exactly why the review step exists — the user always sees and can fix the areas before processing.

## Quick start (local)

```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env        # edit FRONTEND_ORIGINS if needed
uvicorn app.main:app --port 8000

# Frontend (second terminal)
cd frontend
npm install
npm run dev                    # http://localhost:5173
```

Or with Docker: `cp .env.example .env && docker compose up --build` — frontend on :8080, backend on :8000.

Verify it end to end:

```bash
python3 scripts/make_sample_video.py /tmp/sample.mp4
python3 scripts/smoke_test.py /tmp/sample.mp4
```

Full deployment steps (free frontend hosting, VPS/GPU backend, custom domain, HTTPS): **`DEPLOYMENT.md`**.

## Configuration

All backend settings are environment variables — see `.env.example`. The important ones:

| Variable | Default | Meaning |
|---|---|---|
| `RETENTION_HOURS` | 24 | Auto-delete uploaded + processed videos after this long |
| `MAX_UPLOAD_MB` | 500 | Upload size limit |
| `OCR_ENGINE` | auto | `rapidocr` / `easyocr` / `tesseract` |
| `DEFAULT_ENGINE` | cpu | `cpu` or `propainter` |
| `FRONTEND_ORIGINS` | localhost:5173 | CORS allow-list (set to your live domain) |
| `RUNPOD_ENDPOINT_ID` / `RUNPOD_API_KEY` | — | ProPainter GPU (server-side only) |

## License note

ProPainter is an open-source research model — check its repository license before commercial use, and respect the licences of OCR models you deploy. The CLEANFRAME code in this repository is yours to use for your own commercial service.
