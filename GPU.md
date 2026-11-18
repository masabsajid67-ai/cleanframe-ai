# CLEANFRAME AI — ProPainter GPU: how to connect, and what it costs

**Status in v1:** the ProPainter adapter is built and wired (`backend/app/inpaint.py`, `gpu/propainter_worker.py`), but no GPU is connected by default. Until you connect one, the site honestly shows the GPU engine as unavailable and the free CPU engine does all the work. Nothing is faked.

## Why a GPU is needed at all

ProPainter (NeurIPS 2023, "ProPainter: Improving Propagation and Transformer for Video Inpainting") uses optical flow + a transformer to reconstruct moving backgrounds. It needs CUDA and roughly **24 GB of VRAM** for full-resolution work (8 GB can work at reduced settings, slowly). It cannot run on:

- Netlify / Vercel / static hosting (no GPU, no long-running process)
- A phone
- A normal CPU VPS

## Option 1 — RunPod Serverless (recommended)

Pay-per-second, scales to zero (no cost when idle), no server to manage.

### Costs (checked November 2026 — always confirm the live rate in the RunPod console before deploying)

| GPU | VRAM | Approx. rate |
|---|---|---|
| RTX 3090 (Community) | 24 GB | ~$0.34/hour |
| RTX 4090 (Community / Secure) | 24 GB | ~$0.34 / $0.89/hour |
| RTX 4090 (Serverless) | 24 GB | ~$1.10/hour (billed per second, idle = $0) |
| A100 80 GB (Serverless) | 80 GB | ~$2.72/hour |

**Per-video cost on a 3090/4090 endpoint is typically ~$0.05–$0.30** depending on length and resolution (a 30-second clip takes roughly 2–5 minutes of GPU time; a 2–5 minute video roughly 15–45 minutes). Heavy personal use rarely exceeds ~$10/month. RunPod requires adding funds/credit first — start with $10 and watch the first jobs.

### Setup steps

1. **Build the GPU image** (on any machine with Docker):
   ```bash
   cd cleanframe-ai/gpu
   docker build -f Dockerfile.gpu -t <your-registry>/cleanframe-propainter:latest .
   docker push <your-registry>/cleanframe-propainter:latest
   ```
   The Dockerfile clones the official ProPainter repo. You must add the weight download step for the current official weights (links are in the ProPainter README) and verify checksums — weight hosting changes, so they are deliberately not hard-coded here.
2. **Create the endpoint:** RunPod → Serverless → New Endpoint → Container Image = your pushed image → GPU: RTX 3090 or 4090 (add a second GPU type as fallback) → Workers: Min 0, Max 1–3 → Timeout 3600s → Deploy.
3. **Copy the Endpoint ID** and create an **API key** (RunPod → Settings → API Keys).
4. **On the backend only** (Render/Fly/VPS env, never the frontend):
   ```
   PROPINTER_MODE=runpod
   RUNPOD_ENDPOINT_ID=<endpoint id>
   RUNPOD_API_KEY=<api key>
   ```
   Restart the backend. `/api/health` should now show `"propainter_configured": true`, and the workspace enables the ProPainter engine.
5. **Test** with a 10-second clip first. Check the RunPod dashboard for the job cost before running long videos.

The worker contract is: backend sends `{video_b64, regions}` → worker renders a mask video from the regions only → ProPainter inpaints → worker returns `{video_b64}` (silent; the backend re-attaches the original audio). See `gpu/propainter_worker.py`.

## Option 2 — Modal (best free start)

Modal bills per second, scales to zero, and its **Starter plan includes $30/month of free compute** (checked November 2026). Rates: A10 ~$1.10/hour, L40S ~$1.95/hour, A100 80 GB ~$2.50/hour (plus CPU/memory).

1. Wrap `gpu/propainter_worker.py`'s `handler` logic in a Modal function with `gpu="A10G"` and a `.web_endpoint()`, using the same `{video_b64, regions}` → `{video_b64}` contract.
2. `modal deploy` it, copy the `*.modal.run` URL.
3. On the backend only:
   ```
   PROPINTER_MODE=http
   PROPINTER_ENDPOINT_URL=https://<you>--cleanframe-propainter.modal.run
   PROPINTER_API_KEY=<only if you add auth to the endpoint>
   ```
4. Restart and test as above.

Modal may ask for a card on file depending on account/region — if it does, RunPod (prepaid funds) is the alternative.

## Option 3 — Your own GPU machine / Vast.ai pod

Rent an RTX 4090 pod (~$0.26–$0.48/hour median on Vast.ai, November 2026) or use a local NVIDIA GPU machine:

```bash
git clone https://github.com/sczhou/ProPainter.git /opt/ProPainter
# install its requirements + weights per its README
# then on the backend:
PROPINTER_MODE=local
PROPINTER_LOCAL_DIR=/opt/ProPainter
```

The backend calls `inference_propainter.py` directly with a rendered mask video. This only works when the backend itself runs on the GPU machine.

## What NOT to do

- Do not put a RunPod/Modal key in frontend code, in `VITE_*` variables, or in Git. Keys live in backend env only.
- Do not promise clients ProPainter quality until you have run a real test job on your own endpoint and checked the output.
- Do not run long 4K videos through a 24 GB card at full resolution without testing — ProPainter can run out of memory; the worker uses `resize_ratio 1.0`, so start with 720p/1080p clips.

## References

- ProPainter repo: https://github.com/sczhou/ProPainter
- RunPod pricing: https://www.runpod.io/pricing (confirm live rates in console)
- Modal pricing: https://modal.com/pricing
- Price snapshots above were cross-checked against provider pricing pages as of October–November 2026; GPU prices move, so treat them as estimates.
