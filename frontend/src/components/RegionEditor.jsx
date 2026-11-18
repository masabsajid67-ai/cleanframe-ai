import { useRef, useState } from 'react'

/**
 * Manual caption-region editor.
 * - Drag a box to move it, drag its corner handle to resize it.
 * - Drag on empty frame space to draw a new region.
 * - Edit start/end seconds in the list below the frame.
 * All coordinates are normalised 0..1 so they survive any resolution.
 */
export default function RegionEditor({ frameUrl, frameTime, regions, onChange, duration, detectionsForFrame }) {
  const stageRef = useRef(null)
  const [selected, setSelected] = useState(0)
  const [draft, setDraft] = useState(null)
  const dragRef = useRef(null)

  const toNorm = (clientX, clientY) => {
    const r = stageRef.current.getBoundingClientRect()
    return {
      x: Math.max(0, Math.min(1, (clientX - r.left) / r.width)),
      y: Math.max(0, Math.min(1, (clientY - r.top) / r.height)),
    }
  }

  const patch = (i, patchObj) => {
    const next = regions.map((r, j) => (j === i ? { ...r, ...patchObj } : r))
    onChange(next)
  }

  const onStageDown = (e) => {
    if (e.target !== e.currentTarget && !e.target.classList.contains('stage-img')) return
    const p = toNorm(e.clientX, e.clientY)
    dragRef.current = { mode: 'draw', start: p }
    setDraft({ x: p.x, y: p.y, w: 0.01, h: 0.01 })
    stageRef.current.setPointerCapture(e.pointerId)
  }
  const onStageMove = (e) => {
    const d = dragRef.current
    if (!d) return
    const p = toNorm(e.clientX, e.clientY)
    if (d.mode === 'draw') {
      setDraft({
        x: Math.min(d.start.x, p.x), y: Math.min(d.start.y, p.y),
        w: Math.abs(p.x - d.start.x), h: Math.abs(p.y - d.start.y),
      })
    } else if (d.mode === 'move') {
      const dx = p.x - d.last.x, dy = p.y - d.last.y
      d.last = p
      const r = regions[d.index]
      patch(d.index, {
        x: Math.max(0, Math.min(1 - r.w, r.x + dx)),
        y: Math.max(0, Math.min(1 - r.h, r.y + dy)),
      })
    } else if (d.mode === 'resize') {
      const r = regions[d.index]
      patch(d.index, {
        w: Math.max(0.02, Math.min(1 - r.x, p.x - r.x)),
        h: Math.max(0.02, Math.min(1 - r.y, p.y - r.y)),
      })
    }
  }
  const onStageUp = () => {
    const d = dragRef.current
    if (d?.mode === 'draw' && draft && draft.w > 0.02 && draft.h > 0.015) {
      onChange([...regions, { ...draft, start: 0, end: duration || 1e9 }])
      setSelected(regions.length)
    }
    dragRef.current = null
    setDraft(null)
  }

  const boxStyle = (b) => ({
    left: `${b.x * 100}%`, top: `${b.y * 100}%`,
    width: `${b.w * 100}%`, height: `${b.h * 100}%`,
  })

  return (
    <div>
      <div
        className="frame-stage" ref={stageRef}
        onPointerDown={onStageDown} onPointerMove={onStageMove} onPointerUp={onStageUp}
      >
        <img className="stage-img" src={frameUrl} alt={`Video frame at ${frameTime}s`} draggable={false} />
        {(detectionsForFrame || []).map((b, i) => (
          <div key={`det-${i}`} className="region-box" style={{ ...boxStyle(b), borderStyle: 'dashed', pointerEvents: 'none', opacity: 0.85 }}>
            <span className="tag">OCR · {Math.round((b.confidence || 0) * 100)}%</span>
          </div>
        ))}
        {regions.map((r, i) => (
          <div
            key={i} className={`region-box ${selected === i ? 'selected' : ''}`} style={boxStyle(r)}
            onPointerDown={(e) => {
              e.stopPropagation()
              setSelected(i)
              dragRef.current = { mode: 'move', index: i, last: toNorm(e.clientX, e.clientY) }
              stageRef.current.setPointerCapture(e.pointerId)
            }}
          >
            <span className="tag">Region {i + 1} · {r.start ?? 0}s–{r.end >= 1e8 ? 'end' : `${r.end}s`}</span>
            <span
              className="handle"
              onPointerDown={(e) => {
                e.stopPropagation()
                setSelected(i)
                dragRef.current = { mode: 'resize', index: i }
                stageRef.current.setPointerCapture(e.pointerId)
              }}
            />
          </div>
        ))}
        {draft && <div className="region-box selected" style={boxStyle(draft)}><span className="tag">New region</span></div>}
      </div>

      <div className="region-list">
        {regions.length === 0 && (
          <div className="notice info" style={{ margin: 0 }}>
            No regions yet. Drag on the frame above to draw the caption area, or run detection again.
          </div>
        )}
        {regions.map((r, i) => (
          <div className="region-row" key={i}>
            <strong>#{i + 1}</strong>
            <span className="grow">
              {Math.round(r.x * 100)}%, {Math.round(r.y * 100)}% · {Math.round(r.w * 100)}% × {Math.round(r.h * 100)}%
              {r.texts?.length ? ` · “${r.texts.slice(0, 2).join(' / ')}”` : ''}
            </span>
            <label style={{ fontSize: 12, color: '#737373' }}>from
              <input type="number" min="0" step="0.5" value={r.start ?? 0} style={{ width: 64, marginLeft: 4 }}
                onChange={(e) => patch(i, { start: Number(e.target.value) })} />s
            </label>
            <label style={{ fontSize: 12, color: '#737373' }}>to
              <input type="number" min="0" step="0.5" value={r.end >= 1e8 ? (duration || 0) : (r.end ?? 0)} style={{ width: 64, marginLeft: 4 }}
                onChange={(e) => patch(i, { end: Number(e.target.value) })} />s
            </label>
            <button onClick={() => { onChange(regions.filter((_, j) => j !== i)); setSelected(0) }}>Remove</button>
          </div>
        ))}
      </div>
    </div>
  )
}
