import { useCallback, useEffect, useRef, useState } from 'react'
import { api, downloadFile } from './api.js'
import RegionEditor from './components/RegionEditor.jsx'

const ACCEPTED = ['.mp4', '.mov', '.webm']
const STEPS = ['Upload', 'Detect', 'Review', 'Process', 'Download']

function stepIndex(status) {
  return { uploaded: 1, detecting: 1, review: 2, processing: 3, done: 4, error: 2 }[status] ?? 0
}

function ComparePlayer({ jobId }) {
  const [pos, setPos] = useState(50)
  const beforeRef = useRef(null)
  const afterRef = useRef(null)
  const shellRef = useRef(null)

  const sync = (master, slave) => {
    if (!master || !slave) return
    if (Math.abs(master.currentTime - slave.currentTime) > 0.08) slave.currentTime = master.currentTime
  }
  const toggle = () => {
    const a = beforeRef.current, b = afterRef.current
    if (!a || !b) return
    if (a.paused) { sync(a, b); a.play(); b.play() } else { a.pause(); b.pause() }
  }
  const update = (clientX) => {
    const rect = shellRef.current.getBoundingClientRect()
    setPos(Math.max(4, Math.min(96, ((clientX - rect.left) / rect.width) * 100)))
  }

  return (
    <div>
      <div
        className="video-compare" ref={shellRef}
        onPointerDown={(e) => { shellRef.current.setPointerCapture(e.pointerId); update(e.clientX) }}
        onPointerMove={(e) => { if (e.buttons) update(e.clientX) }}
      >
        <video ref={beforeRef} src={api.originalUrl(jobId)} muted playsInline preload="metadata"
          onTimeUpdate={(e) => sync(e.target, afterRef.current)} />
        <div className="after-layer" style={{ clipPath: `inset(0 0 0 ${pos}%)` }}>
          <video ref={afterRef} src={api.downloadUrl(jobId)} muted playsInline preload="metadata" />
        </div>
        <div className="vc-handle" style={{ left: `${pos}%` }} />
        <span className="vc-tag left">BEFORE</span>
        <span className="vc-tag right">AFTER</span>
      </div>
      <div className="video-controls">
        <button className="btn btn-dark btn-sm" onClick={toggle}>▶ Play both / Pause</button>
        <button className="btn btn-ghost btn-sm" onClick={() => {
          const v = beforeRef.current; if (v) { v.currentTime = 0; if (afterRef.current) afterRef.current.currentTime = 0 }
        }}>↺ Restart</button>
        <span style={{ fontSize: 13.5, color: '#737373' }}>Drag the handle to compare. Both videos stay in sync.</span>
      </div>
    </div>
  )
}

export default function Workspace({ pendingFile, onConsumed }) {
  const [file, setFile] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [uploadPct, setUploadPct] = useState(null)
  const [job, setJob] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [health, setHealth] = useState(null)
  const [regions, setRegions] = useState([])
  const [frameIndex, setFrameIndex] = useState(0)
  const [detections, setDetections] = useState([])
  const [engine, setEngine] = useState('cpu')
  const [downloading, setDownloading] = useState(false)
  const inputRef = useRef(null)
  const pollRef = useRef(null)

  const refresh = useCallback(async (id) => {
    try { const j = await api.getJob(id); setJob(j); return j } catch { return null }
  }, [])

  useEffect(() => { api.health().then(setHealth).catch(() => {}) }, [])

  // Poll while the server is working — progress shown is the server's real progress.
  useEffect(() => {
    if (job && (job.status === 'detecting' || job.status === 'processing')) {
      pollRef.current = setInterval(() => refresh(job.job_id), 1500)
      return () => clearInterval(pollRef.current)
    }
  }, [job?.status, job?.job_id, refresh])

  useEffect(() => {
    if (job?.status === 'review' && job.regions) setRegions(job.regions)
  }, [job?.status]) // eslint-disable-line react-hooks/exhaustive-deps

  const startUpload = useCallback(async (f) => {
    if (!f) return
    setError(''); setJob(null); setRegions([]); setDetections([]); setFrameIndex(0)
    setUploadPct(0); setBusy(true)
    try {
      const created = await api.upload(f, setUploadPct)
      setJob(created)
      setUploadPct(null)
      await api.detect(created.job_id)
      await refresh(created.job_id)
    } catch (e) {
      setError(e.message); setUploadPct(null)
    } finally { setBusy(false) }
  }, [refresh])

  useEffect(() => {
    if (pendingFile) { setFile(pendingFile); startUpload(pendingFile); onConsumed?.() }
  }, [pendingFile, startUpload, onConsumed])

  const pick = (f) => {
    if (!f) return
    const ext = '.' + (f.name.split('.').pop() || '').toLowerCase()
    if (!ACCEPTED.includes(ext)) { setError(`Only MP4, MOV and WEBM are supported. You selected: ${f.name}`); return }
    setFile(f); startUpload(f)
  }

  const loadDetections = async () => {
    if (!job) return
    try { const d = await api.detections(job.job_id); setDetections(d.detections || []) } catch {}
  }
  useEffect(() => { if (job?.status === 'review') loadDetections() }, [job?.status]) // eslint-disable-line

  const saveAndProcess = async () => {
    if (!job) return
    setError(''); setBusy(true)
    try {
      await api.saveRegions(job.job_id, regions)
      await api.process(job.job_id, engine, regions)
      await refresh(job.job_id)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const doDownload = async () => {
    if (!job) return
    setDownloading(true); setError('')
    try { await downloadFile(job.job_id) } catch (e) { setError(e.message) } finally { setDownloading(false) }
  }

  const deleteNow = async () => {
    if (!job) return
    if (!window.confirm('Delete the uploaded and processed videos from the server right now?')) return
    try { await api.deleteJob(job.job_id) } catch {}
    setJob(null); setFile(null); setRegions([]); setDetections([])
  }

  const frames = job?.detection?.preview_frames || []
  const currentDet = detections.find((d) => d.index === frameIndex)
  const duration = job?.video?.duration || 0
  const active = stepIndex(job?.status || 'idle')

  return (
    <main className="wrap ws">
      <div className="steps">
        {STEPS.map((s, i) => (
          <span key={s} className={`step ${i === active ? 'active' : ''} ${i < active ? 'done' : ''}`}>
            {i < active ? '✓' : i + 1} {s}
          </span>
        ))}
      </div>

      {!job && (
        <div className="panel">
          <h2>Upload your video</h2>
          <p className="hint">MP4, MOV or WEBM — up to {health?.max_upload_mb || 500} MB. Only captions are removed; everything else is preserved.</p>
          {error && <div className="notice error">{error}</div>}
          <div
            className={`dropzone ${dragging ? 'dragging' : ''}`} style={{ margin: 0, maxWidth: 'none' }}
            role="button" tabIndex={0}
            onClick={() => inputRef.current.click()}
            onKeyDown={(e) => { if (e.key === 'Enter') inputRef.current.click() }}
            onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); pick(e.dataTransfer.files[0]) }}
          >
            <div className="dz-icon">↑</div>
            <h3>{file ? file.name : 'Drop your video here'}</h3>
            <p>or click to browse your files</p>
            <div className="formats"><span>MP4</span><span>MOV</span><span>WEBM</span></div>
            <input ref={inputRef} type="file" accept=".mp4,.mov,.webm,video/mp4,video/quicktime,video/webm" hidden
              onChange={(e) => pick(e.target.files[0])} />
          </div>
          {uploadPct !== null && (
            <div style={{ marginTop: 18 }}>
              <div className="progress-row">
                <div className="progress-track" style={{ flex: 1 }}><div className="progress-fill" style={{ width: `${uploadPct}%` }} /></div>
                <span className="pct">{uploadPct}%</span>
              </div>
              <p className="hint" style={{ margin: '8px 0 0' }}>Uploading… please keep this tab open.</p>
            </div>
          )}
          {health && (
            <p className="hint" style={{ marginTop: 16 }}>
              Server: OCR engine <strong>{health.ocr_engine}</strong> · ProPainter GPU: <strong>{health.propainter_configured ? 'connected' : 'not connected — CPU engine available'}</strong> · Files auto-deleted after {health.retention_hours}h.
            </p>
          )}
        </div>
      )}

      {job && (
        <>
          <div className="panel">
            <h2>{job.filename}</h2>
            <p className="hint">{job.stage || job.status}
              {(job.status === 'detecting' || job.status === 'processing') && (
                <span className="stage-dots"><span /><span /><span /></span>
              )}
            </p>
            {error && <div className="notice error">{error}</div>}
            {job.error && <div className="notice error"><strong>Processing stopped:</strong> {job.error}</div>}

            {(job.status === 'detecting' || job.status === 'processing') && (
              <div className="loader-row" style={{ marginBottom: 16 }}>
                <div className="spinner" />
                <div style={{ flex: 1 }}>
                  <div className="progress-row">
                    <div className="progress-track" style={{ flex: 1 }}><div className="progress-fill" style={{ width: `${job.progress || 0}%` }} /></div>
                    <span className="pct">{job.progress || 0}%</span>
                  </div>
                  <p className="hint" style={{ margin: '8px 0 0' }}>
                    {job.status === 'detecting'
                      ? 'Reading frames and finding caption text with OCR…'
                      : 'Rebuilding the background behind the captions, frame by frame. Original resolution and audio are preserved.'}
                  </p>
                </div>
              </div>
            )}

            {job.video && (
              <div className="meta-table">
                <div>Resolution<b>{job.video.width} × {job.video.height}</b></div>
                <div>Duration<b>{job.video.duration?.toFixed(1)}s</b></div>
                <div>Frame rate<b>{job.video.fps} fps</b></div>
                <div>Audio<b>{job.video.has_audio ? 'Yes — will be preserved' : 'None'}</b></div>
                <div>Size<b>{(job.size / 1048576).toFixed(1)} MB</b></div>
              </div>
            )}
          </div>

          {job.status === 'review' && job.detection && (
            <div className="panel">
              <h2>Review detected caption areas</h2>
              <p className="hint">
                {job.detection.total_boxes} text box{job.detection.total_boxes === 1 ? '' : 'es'} found
                {job.detection.avg_confidence ? ` · average confidence ${Math.round(job.detection.avg_confidence * 100)}%` : ''}
                {' '}· OCR engine: {job.detection.engine}. Only these areas will be changed.
              </p>
              {job.detection.needs_review && (
                <div className="notice warn"><strong>Please review before processing.</strong> {job.detection.review_reason} Drag a box to move it, drag its corner to resize it, or drag on the frame to draw a new caption area.</div>
              )}
              {!job.detection.needs_review && (
                <div className="notice ok">Detection looks confident. You can still adjust any area below before processing.</div>
              )}

              {frames.length > 0 && (
                <>
                  <RegionEditor
                    frameUrl={api.frameUrl(job.job_id, frameIndex)}
                    frameTime={frames[frameIndex]?.time || 0}
                    regions={regions}
                    onChange={setRegions}
                    duration={duration}
                    detectionsForFrame={currentDet?.boxes || []}
                  />
                  <div className="frame-nav">
                    <button className="btn btn-ghost btn-sm" disabled={frameIndex === 0} onClick={() => setFrameIndex((i) => Math.max(0, i - 1))}>← Prev frame</button>
                    <input type="range" min="0" max={frames.length - 1} value={frameIndex} onChange={(e) => setFrameIndex(Number(e.target.value))} />
                    <button className="btn btn-ghost btn-sm" disabled={frameIndex >= frames.length - 1} onClick={() => setFrameIndex((i) => Math.min(frames.length - 1, i + 1))}>Next frame →</button>
                    <span style={{ fontSize: 13.5, color: '#737373' }}>Frame {frameIndex + 1} / {frames.length} · {frames[frameIndex]?.time}s</span>
                  </div>
                </>
              )}

              <h3 style={{ margin: '26px 0 4px' }}>Processing engine</h3>
              <div className="engine-pick">
                <button className={`engine-card ${engine === 'cpu' ? 'selected' : ''}`} onClick={() => setEngine('cpu')}>
                  <h3>CPU Engine — Free</h3>
                  <p>OpenCV inpainting on this server. No GPU needed. Best on plain and slow-moving backgrounds.</p>
                  <span className="badge">ALWAYS AVAILABLE</span>
                </button>
                <button
                  className={`engine-card ${engine === 'propainter' ? 'selected' : ''} ${health && !health.propainter_configured ? 'disabled' : ''}`}
                  disabled={health && !health.propainter_configured}
                  onClick={() => setEngine('propainter')}
                >
                  <h3>ProPainter — GPU</h3>
                  <p>AI video inpainting with motion-aware reconstruction. Needs a connected GPU (RunPod / Modal).</p>
                  <span className="badge">{health?.propainter_configured ? 'CONNECTED' : 'GPU NOT CONNECTED'}</span>
                </button>
              </div>
              {health && !health.propainter_configured && (
                <div className="notice info">
                  ProPainter is not connected on this server yet. The CPU engine works now. To connect a GPU, the operator sets the RunPod endpoint in the backend environment — see <strong>GPU.md</strong> in the project. Typical cost is about $0.05–$0.30 per short video on RunPod.
                </div>
              )}

              <div className="video-controls">
                <button className="btn btn-dark" disabled={busy || regions.length === 0} onClick={saveAndProcess}>
                  {busy ? 'Starting…' : `Remove Captions (${regions.length} region${regions.length === 1 ? '' : 's'}) →`}
                </button>
                <button className="btn btn-ghost" onClick={async () => { setError(''); await api.detect(job.job_id); refresh(job.job_id) }}>
                  Re-run detection
                </button>
                <button className="btn btn-ghost" onClick={deleteNow}>Delete video now</button>
              </div>
            </div>
          )}

          {job.status === 'done' && (
            <div className="panel">
              <h2>Your clean video is ready</h2>
              <p className="hint">
                Engine: {job.engine || 'cpu'} · Output: {job.output_video?.width} × {job.output_video?.height} · {job.output_video?.has_audio ? 'original audio preserved' : 'no audio track'}
                {job.output_size ? ` · ${(job.output_size / 1048576).toFixed(1)} MB` : ''}
              </p>
              <ComparePlayer jobId={job.job_id} />
              <div className="video-controls" style={{ marginTop: 20 }}>
                <button className="btn btn-dark btn-lg" disabled={downloading} onClick={doDownload}>
                  {downloading ? 'Preparing…' : '⬇ Download Clean Video'}
                </button>
                <button className="btn btn-ghost" onClick={() => { setJob(null); setFile(null); setRegions([]); setDetections([]) }}>Process another video</button>
                <button className="btn btn-ghost" onClick={deleteNow}>Delete from server</button>
              </div>
              <p className="hint" style={{ marginTop: 14 }}>Files delete automatically after the server retention period. Download now to keep your copy.</p>
            </div>
          )}

          {job.status === 'error' && (
            <div className="panel">
              <div className="video-controls" style={{ marginTop: 0 }}>
                <button className="btn btn-dark" onClick={() => { setJob(null); setFile(null); setRegions([]) }}>Try another video</button>
                <button className="btn btn-ghost" onClick={deleteNow}>Delete from server</button>
              </div>
            </div>
          )}
        </>
      )}
    </main>
  )
}
