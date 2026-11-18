// All backend calls live here. No API key is ever used in this file —
// the backend holds every secret server-side (see backend/.env).
// Set VITE_API_URL at build time, e.g. https://api.your-domain.com
// Leave it empty and the app talks to the same origin (or the Vite proxy in dev).
const API = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

async function handle(res) {
  const text = await res.text()
  let data = {}
  try { data = JSON.parse(text) } catch { data = { detail: text } }
  if (!res.ok) {
    const msg = data.detail || data.message || `Request failed (${res.status})`
    const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
    err.status = res.status
    throw err
  }
  return data
}

export const api = {
  health: () => fetch(`${API}/api/health`).then(handle),

  upload: async (file, onProgress) => {
    // XMLHttpRequest is used only so upload progress is real, not faked.
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', `${API}/api/jobs/upload`)
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100))
      }
      xhr.onload = () => {
        let data = {}
        try { data = JSON.parse(xhr.responseText) } catch {}
        if (xhr.status >= 200 && xhr.status < 300) resolve(data)
        else reject(new Error(data.detail || `Upload failed (${xhr.status})`))
      }
      xhr.onerror = () => reject(new Error('Upload failed — is the backend running?'))
      const form = new FormData()
      form.append('video', file)
      xhr.send(form)
    })
  },

  getJob: (id) => fetch(`${API}/api/jobs/${id}`).then(handle),
  detect: (id) => fetch(`${API}/api/jobs/${id}/detect`, { method: 'POST' }).then(handle),
  detections: (id) => fetch(`${API}/api/jobs/${id}/detections`).then(handle),
  saveRegions: (id, regions) =>
    fetch(`${API}/api/jobs/${id}/regions`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ regions }),
    }).then(handle),
  process: (id, engine, regions) =>
    fetch(`${API}/api/jobs/${id}/process`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ engine, regions }),
    }).then(handle),
  deleteJob: (id) => fetch(`${API}/api/jobs/${id}`, { method: 'DELETE' }).then(handle),

  frameUrl: (id, index) => `${API}/api/jobs/${id}/frame?index=${index}`,
  originalUrl: (id) => `${API}/api/jobs/${id}/original`,
  downloadUrl: (id) => `${API}/api/jobs/${id}/download`,
}

export async function downloadFile(id, filename = 'cleanframe-output.mp4') {
  const res = await fetch(api.downloadUrl(id))
  if (!res.ok) throw new Error('Download is not ready yet')
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
