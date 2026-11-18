# CLEANFRAME AI — Deployment, step by step

No purchase is required to follow this guide. The frontend can be hosted free. The backend needs a server that can run Python + FFmpeg — a free tier works for testing, a small VPS works for real clients, and a GPU is only needed for the ProPainter engine (see `GPU.md`).

**Architecture in one line:** static frontend (free) → FastAPI backend (VPS / container host) → optional GPU endpoint (RunPod, pay-per-second).

---

## Step 0 — Before you start

You need, all free to create:

1. A GitHub account (to hold the code and to deploy from).
2. A Netlify or Vercel account (free tier, for the frontend).
3. A backend host account — pick one in Step 2.
4. (Optional, later) A RunPod account — only if you want ProPainter. Do **not** buy credits until you have tested the CPU engine live.

Put the code in GitHub first so every host below can deploy from the same source:

```bash
cd cleanframe-ai
git init && git add . && git commit -m "CLEANFRAME AI v1"
# create an empty repo on GitHub, then:
git remote add origin https://github.com/<you>/cleanframe-ai.git
git branch -M main && git push -u origin main
```

> `.gitignore` already excludes `.env`, secrets and stored videos. Never commit a real `.env` file.

---

## Step 1 — Deploy the backend (the part that does the work)

The backend **cannot** run on Netlify/Vercel static hosting — it runs FFmpeg and OpenCV and holds video files. Pick one:

### Option A — Render (easiest, free tier exists)

1. Render dashboard → **New → Web Service** → connect your GitHub repo.
2. Root directory: `backend`. Environment: **Docker** (it will use `backend/Dockerfile`).
3. Plan: Free for testing (sleeps when idle, slower first request; fine for demos). For clients use **Starter (~$7/month)** so it stays awake.
4. Environment variables (Render → Environment):
   - `FRONTEND_ORIGINS` = your frontend URL (add it after Step 2, then redeploy)
   - `RETENTION_HOURS` = `24`
   - `MAX_UPLOAD_MB` = `500`
   - Leave the RunPod variables empty until you connect a GPU.
5. Deploy. Note the URL, e.g. `https://cleanframe-api.onrender.com`.
6. Test: open `https://cleanframe-api.onrender.com/api/health` — you should see `{"status":"ok", ...}`.

### Option B — Fly.io (Docker, generous free allowance)

```bash
curl -L https://fly.io/install.sh | sh
fly auth login
cd backend
fly launch --no-deploy   # pick a region near your users, 1GB RAM minimum
fly secrets set FRONTEND_ORIGINS="https://<your-frontend-domain>"
fly deploy
fly open   # note the https URL
```

### Option C — Any VPS (Hetzner / DigitalOcean / Contabo, ~€4–6/month)

Best value for real client use: no sleeping, local disk for videos, easy to scale.

```bash
# On the VPS (Ubuntu 24.04):
sudo apt update && sudo apt install -y docker.io docker-compose-v2 git
git clone https://github.com/<you>/cleanframe-ai.git && cd cleanframe-ai
cp .env.example .env && nano .env   # set FRONTEND_ORIGINS to your domain
docker compose up -d --build
# Backend on :8000, frontend on :8080. Put Caddy/nginx + HTTPS in front (Step 3).
```

**Minimum backend specs:** 2 vCPU, 2 GB RAM, 20 GB disk for the CPU engine. 1080p videos are slower on 1 vCPU — use 2+ for clients.

---

## Step 2 — Deploy the frontend (free)

### Netlify (recommended for this project)

1. Netlify → **Add new site → Import an existing project** → GitHub → your repo.
2. Build settings:
   - Base directory: `frontend`
   - Build command: `npm run build`
   - Publish directory: `frontend/dist`
3. Environment variable: `VITE_API_URL` = your backend URL from Step 1 (e.g. `https://cleanframe-api.onrender.com`). No trailing slash. **No keys go here.**
4. Deploy. Netlify gives you a free `*.netlify.app` URL.
5. Go back to the backend and set `FRONTEND_ORIGINS` to that exact URL, then redeploy/restart the backend. (CORS will block uploads until this matches.)

### Vercel (alternative)

Same settings: root directory `frontend`, framework **Vite**, build `npm run build`, output `dist`, env `VITE_API_URL` = backend URL.

> The frontend uses hash routing (`#/workspace`), so no redirect rules are needed on either host.

---

## Step 3 — Custom domain + HTTPS (optional, recommended for clients)

1. Buy/connect a domain only when you are ready (no purchase is made by this guide). In Netlify/Vercel: **Domain settings → Add domain** → add the DNS records they show.
2. HTTPS is automatic and free on Netlify/Vercel/Render/Fly.io.
3. Update `FRONTEND_ORIGINS` on the backend to the new domain and restart it.
4. Rebuild the frontend if `VITE_API_URL` changed (it is baked in at build time).

---

## Step 4 — Test the live site end to end

1. Open the site → **Upload Your Video** → upload a short MP4 with burned-in captions (make one with `scripts/make_sample_video.py` if needed).
2. Wait for detection → check the boxes on the frames → adjust one box → **Remove Captions**.
3. Compare Before/After → **Download Clean Video** → open it: same size, same audio, captions gone.
4. Delete the job from the workspace, then check `/api/health` still answers.
5. If upload fails with a CORS/network error: `VITE_API_URL` and `FRONTEND_ORIGINS` do not match — fix those two values first.

## Step 5 — Connect ProPainter (optional, paid per use)

Follow **`GPU.md`**. In short: create a RunPod serverless endpoint from `gpu/Dockerfile.gpu`, then set `RUNPOD_ENDPOINT_ID` + `RUNPOD_API_KEY` on the backend only. The frontend automatically shows the GPU engine as connected.

## Step 6 — Going commercial (checklist)

- [ ] Backend on a paid plan that does not sleep (Render Starter / VPS).
- [ ] `RETENTION_HOURS` set to your promised policy; Privacy/Terms pages match it.
- [ ] Storage disk monitored — videos are deleted automatically, but a traffic spike still needs headroom.
- [ ] Rate limiting / auth added before public launch if you charge per video (not included in v1 — add it as the next feature, not as an afterthought).
- [ ] ProPainter licence checked for your commercial use.
- [ ] Backups: this app stores nothing permanent, so there is nothing to back up except the code and env values.

## Troubleshooting

| Symptom | Most likely cause | Fix |
|---|---|---|
| Upload button does nothing / network error | Backend URL wrong or backend asleep | Check `VITE_API_URL`, open `/api/health` directly |
| CORS error in browser console | `FRONTEND_ORIGINS` mismatch | Set it to the exact frontend origin, restart backend |
| Detection finds nothing | Stylised/tiny text, or no OCR installed | Draw regions manually; check `ocr_engine` in `/api/health` |
| Processing is very slow | 1 vCPU / long 1080p video | Bigger instance, or shorter test video first |
| ProPainter button disabled | GPU not configured | Expected — see `GPU.md`; CPU engine still works |
| `ffmpeg: command not found` | Backend installed without FFmpeg | Use the provided Dockerfile / install ffmpeg |
