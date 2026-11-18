import { useEffect, useRef, useState } from 'react'
import Workspace from './Workspace.jsx'

const ACCEPTED = ['.mp4', '.mov', '.webm']

function useHashRoute() {
  const [route, setRoute] = useState(() => window.location.hash.replace('#', '') || '/')
  useEffect(() => {
    const onHash = () => setRoute(window.location.hash.replace('#', '') || '/')
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  return route
}

function go(path) { window.location.hash = path }

function CompareDemo() {
  const [pos, setPos] = useState(50)
  const ref = useRef(null)
  const update = (clientX) => {
    const rect = ref.current.getBoundingClientRect()
    setPos(Math.max(4, Math.min(96, ((clientX - rect.left) / rect.width) * 100)))
  }
  return (
    <div className="compare-shell">
      <div
        className="compare-demo"
        ref={ref}
        onPointerDown={(e) => { ref.current.setPointerCapture(e.pointerId); update(e.clientX) }}
        onPointerMove={(e) => { if (e.buttons) update(e.clientX) }}
      >
        <div className="scene">
          <div>
            <div className="face">🎬</div>
            <p>Your scene — faces, movement and colours stay exactly as they were.</p>
          </div>
        </div>
        <div className="caption-bar">This is the burned-in caption</div>
        <div className="after" style={{ clipPath: `inset(0 0 0 ${pos}%)` }}>
          <div className="scene">
            <div>
              <div className="face">🎬</div>
              <p>Caption gone. Background rebuilt. Nothing else touched.</p>
            </div>
          </div>
        </div>
        <div className="compare-handle" style={{ left: `${pos}%` }} />
      </div>
      <div className="compare-labels"><span>← BEFORE</span><span>AFTER →</span></div>
    </div>
  )
}

function Dropzone({ onFile }) {
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef(null)
  const pick = (file) => {
    if (!file) return
    const ext = '.' + (file.name.split('.').pop() || '').toLowerCase()
    if (!ACCEPTED.includes(ext)) {
      alert(`Please choose an MP4, MOV or WEBM file. You selected: ${file.name}`)
      return
    }
    onFile(file)
  }
  return (
    <div
      className={`dropzone ${dragging ? 'dragging' : ''}`}
      role="button" tabIndex={0}
      onClick={() => inputRef.current.click()}
      onKeyDown={(e) => { if (e.key === 'Enter') inputRef.current.click() }}
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => { e.preventDefault(); setDragging(false); pick(e.dataTransfer.files[0]) }}
    >
      <div className="dz-icon">↑</div>
      <h3>Drop your video here</h3>
      <p>or click to browse your files. Your video is processed privately and deleted automatically.</p>
      <div className="formats"><span>MP4</span><span>MOV</span><span>WEBM</span><span>UP TO 500 MB</span></div>
      <input ref={inputRef} type="file" accept=".mp4,.mov,.webm,video/mp4,video/quicktime,video/webm" hidden
        onChange={(e) => pick(e.target.files[0])} />
    </div>
  )
}

function Home({ onFile }) {
  return (
    <>
      <section className="hero wrap">
        <span className="pill"><span className="dot" /> AI caption removal — one job, done properly</span>
        <h1>Remove Video Captions.<br /><span className="serif">Keep Everything Else.</span></h1>
        <p className="sub">Clean your videos with AI-powered caption removal.</p>
        <div className="hero-cta">
          <button className="btn btn-dark btn-lg" onClick={() => document.querySelector('.dropzone')?.scrollIntoView({ behavior: 'smooth', block: 'center' })}>
            Upload Your Video ↑
          </button>
          <button className="btn btn-light btn-lg" onClick={() => go('/workspace')}>Open Workspace</button>
        </div>
        <p className="hero-meta">Original resolution · Original audio · No cropping, no zooming</p>
        <Dropzone onFile={onFile} />
      </section>

      <section className="section wrap">
        <h2>How it works</h2>
        <p className="lead">Three steps. You stay in control of exactly what gets removed.</p>
        <div className="grid-3">
          <div className="card"><div className="num">01</div><h3>Upload</h3><p>Drop in an MP4, MOV or WEBM video. It stays in temporary private storage — never shared, never sold.</p></div>
          <div className="card"><div className="num">02</div><h3>Review the detection</h3><p>OCR finds the captions and shows you the exact areas. If detection is uncertain, you review first — and you can move, resize or redraw any area.</p></div>
          <div className="card"><div className="num">03</div><h3>Download clean video</h3><p>Only the caption areas are reconstructed. Compare before and after, then download with your original audio and resolution intact.</p></div>
        </div>
      </section>

      <section className="section wrap" style={{ paddingTop: 0 }}>
        <h2>Before &amp; after</h2>
        <p className="lead">Drag the handle. This is what caption-only removal looks like.</p>
        <CompareDemo />
      </section>

      <section className="section wrap" style={{ paddingTop: 0 }}>
        <div className="promise">
          <div className="yes">
            <h3>✓ What CLEANFRAME removes</h3>
            <ul>
              <li>Burned-in subtitles and captions</li>
              <li>Visible text overlays in the caption area</li>
              <li>Only inside areas you approve</li>
            </ul>
          </div>
          <div className="no">
            <h3>✕ What it never touches</h3>
            <ul>
              <li>Faces, people, logos and objects</li>
              <li>Scenery, movement and colours outside captions</li>
              <li>No general object removal. No background removal.</li>
            </ul>
          </div>
        </div>
      </section>

      <section className="section wrap" style={{ paddingTop: 0, textAlign: 'center' }}>
        <h2>Your video, cleaned — not cropped.</h2>
        <p className="lead">We never hide captions by cropping or zooming. The background behind the text is rebuilt, frame by frame.</p>
        <button className="btn btn-dark btn-lg" onClick={() => go('/workspace')}>Upload Your Video ↑</button>
      </section>
    </>
  )
}

function Privacy() {
  return (
    <main className="wrap legal">
      <h1>Privacy Policy</h1>
      <p><strong>Last updated:</strong> 18 November 2026. CLEANFRAME AI does one thing: remove captions from videos you upload. This policy explains what happens to those videos.</p>
      <h2>1. What we process</h2>
      <p>When you upload a video, we temporarily store the original file and the processed result so the service can work. We do not ask for your name, email or payment details to use the core service, and we do not build profiles about you.</p>
      <h2>2. Automatic deletion</h2>
      <p>Uploaded and processed videos are deleted automatically after the retention period configured on the server (24 hours by default). You can also delete a job immediately from the workspace at any time. After deletion, files are not recoverable from our storage.</p>
      <h2>3. What we never do</h2>
      <ul>
        <li>We never sell, share or publish your videos.</li>
        <li>We never use your videos to train models.</li>
        <li>We never expose API keys or credentials in the website code.</li>
        <li>We never keep videos longer than the retention period.</li>
      </ul>
      <h2>4. GPU processing (optional)</h2>
      <p>If the ProPainter GPU engine is enabled, video data is sent to the configured GPU provider solely to perform inpainting, under that provider&apos;s own privacy terms. The CPU engine processes video only on the CLEANFRAME server.</p>
      <h2>5. Security</h2>
      <p>Videos are stored under random, unguessable job identifiers and are served only through the job&apos;s own download endpoints. No public directory listing exists. Despite these measures, no internet service can guarantee absolute security — do not upload videos you cannot afford to lose control of.</p>
      <h2>6. Your rights</h2>
      <p>You may delete your uploaded and processed videos at any time from the workspace, and you may stop using the service at any time. For privacy questions, contact the site operator through the contact details shown on the site.</p>
    </main>
  )
}

function Terms() {
  return (
    <main className="wrap legal">
      <h1>Terms of Service</h1>
      <p><strong>Last updated:</strong> 18 November 2026. By using CLEANFRAME AI you agree to these terms.</p>
      <h2>1. The service</h2>
      <p>CLEANFRAME AI removes visible captions and subtitles from videos you upload and returns a processed video. The service is provided for lawful use only.</p>
      <h2>2. Your content and rights</h2>
      <p>You must own the video or have permission to process it, including permission to remove its captions. Removing captions from content you do not have rights to may infringe copyright or other rights — that responsibility is yours. You keep all rights in your videos.</p>
      <h2>3. Acceptable use</h2>
      <ul>
        <li>Do not upload illegal content, or content you have no right to process.</li>
        <li>Do not use the service to remove watermarks, logos or ownership marks from other people&apos;s work. CLEANFRAME is built for captions only.</li>
        <li>Do not abuse the service, overload it, or try to access other users&apos; jobs.</li>
      </ul>
      <h2>4. Results</h2>
      <p>Caption removal reconstructs the background behind text. Results depend on the video: plain and slow-moving backgrounds clean best; fast, detailed motion behind text may leave softness or artefacts. The CPU engine and the ProPainter GPU engine can produce different results. No result is guaranteed to be perfect or identical to the original scene.</p>
      <h2>5. Availability and limits</h2>
      <p>Supported formats are MP4, MOV and WEBM, up to the size limit shown on the site. Processing time depends on video length, resolution and server load. The service may be unavailable during maintenance.</p>
      <h2>6. Liability</h2>
      <p>To the maximum extent permitted by law, the service is provided &quot;as is&quot; without warranties, and the operator is not liable for loss of content, processing results, or indirect damages. Keep a copy of your original video — processed output does not replace it.</p>
      <h2>7. Changes</h2>
      <p>These terms may change; the updated date above will change with them. Continued use after a change means you accept the new terms.</p>
    </main>
  )
}

export default function App() {
  const route = useHashRoute()
  const [pendingFile, setPendingFile] = useState(null)
  const [health, setHealth] = useState(null)

  useEffect(() => {
    fetch('/api/health').then((r) => r.json()).then(setHealth).catch(() => {})
  }, [])

  const onFile = (file) => { setPendingFile(file); go('/workspace') }

  return (
    <>
      <header className="nav">
        <div className="wrap nav-inner">
          <a className="logo" onClick={() => go('/')}><span className="logo-mark">◧</span><span>CLEAN<em>FRAME</em> AI</span></a>
          <nav className="nav-links">
            <button className="hide-m" onClick={() => go('/')}>Home</button>
            <button className="hide-m" onClick={() => go('/privacy')}>Privacy</button>
            <button className="hide-m" onClick={() => go('/terms')}>Terms</button>
            <button className="btn btn-dark btn-sm" onClick={() => go('/workspace')}>Upload Video</button>
          </nav>
        </div>
      </header>

      {route === '/' && <Home onFile={onFile} />}
      {route === '/workspace' && <Workspace pendingFile={pendingFile} onConsumed={() => setPendingFile(null)} />}
      {route === '/privacy' && <Privacy />}
      {route === '/terms' && <Terms />}

      <footer className="footer">
        <div className="wrap">
          <div className="footer-inner">
            <span className="logo" style={{ fontSize: 16 }}><span className="logo-mark" style={{ width: 28, height: 28, fontSize: 14 }}>◧</span><span>CLEAN<em>FRAME</em> AI</span></span>
            <nav>
              <button onClick={() => go('/')}>Home</button>
              <button onClick={() => go('/workspace')}>Workspace</button>
              <button onClick={() => go('/privacy')}>Privacy Policy</button>
              <button onClick={() => go('/terms')}>Terms of Service</button>
            </nav>
          </div>
          <small>
            Remove video captions. Keep everything else. Videos are deleted automatically after the server retention period.
            {health ? ` · OCR: ${health.ocr_engine} · GPU ProPainter: ${health.propainter_configured ? 'connected' : 'not connected'}` : ''}
          </small>
        </div>
      </footer>
    </>
  )
}
