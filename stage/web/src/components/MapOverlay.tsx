import { useEffect, useRef, useState } from 'react'

import type { SiteView } from '@/components/CrawlView'
import { Button } from '@/components/ui/8bit/button'
import { postJson, type StageState } from '@/lib/stage'

interface Level {
  kind: 'site' | 'map'
  id: string
  name: string
}

interface MapView {
  id: string
  name: string
  up: string | null
  here: string | null
  places: { id: string; name: string; icon: string; at: [number, number]; visited: boolean }[]
  routes: { a: string; b: string; travel: string }[]
}

// Flat colors for the site overview (the crawl view has the tiles).
const SITE_COLORS: Record<string, string> = {
  '#': '#4a4e69',
  '.': '#9a8c98',
  '+': '#c9a96e',
  "'": '#c9a96e',
  '<': '#7fd1a8',
}

function SiteMap({ id, version }: { id: string; version: number }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const [view, setView] = useState<SiteView | null>(null)

  useEffect(() => {
    fetch(`/api/site/${encodeURIComponent(id)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then(setView)
      .catch(() => setView(null))
  }, [id, version])

  const cell = view ? Math.max(4, Math.min(14, Math.floor(640 / view.w))) : 8
  useEffect(() => {
    const ctx = canvas.current?.getContext('2d')
    if (!ctx || !view) return
    ctx.fillStyle = '#000'
    ctx.fillRect(0, 0, view.w * cell, view.h * cell)
    view.cells.forEach((row, y) =>
      [...row].forEach((c, x) => {
        if (c === ' ') return
        ctx.fillStyle = SITE_COLORS[c] ?? '#9a8c98'
        ctx.globalAlpha = view.visible[y][x] === '1' ? 1 : 0.55
        ctx.fillRect(x * cell, y * cell, cell, cell)
      }),
    )
    ctx.globalAlpha = 1
    ctx.fillStyle = '#e07a3f'
    for (const p of view.pois) ctx.fillRect(p.x * cell + 1, p.y * cell + 1, cell - 2, cell - 2)
    ctx.fillStyle = '#55ff33'
    ctx.fillRect(view.party[0] * cell, view.party[1] * cell, cell, cell)
  }, [view, cell])

  if (!view) return <p className="text-[var(--dim)]">Nothing explored yet.</p>
  return (
    <div className="flex flex-col gap-3">
      <div className="overflow-auto">
        <canvas ref={canvas} width={view.w * cell} height={view.h * cell} className="pixelated max-w-none" />
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-base text-[var(--dim)]">
        <li><span className="mr-1 inline-block size-3 bg-[#55ff33]" />You</li>
        <li><span className="mr-1 inline-block size-3 bg-[#e07a3f]" />Found</li>
        <li><span className="mr-1 inline-block size-3 bg-[#7fd1a8]" />Way out</li>
        {view.pois.map((p) => (
          <li key={p.id} className="text-[var(--parchment)]">{p.name}</li>
        ))}
      </ul>
    </div>
  )
}

const GAP = 96

function GraphMap({ id, version, canAct, onTravel }: { id: string; version: number; canAct: boolean; onTravel: () => void }) {
  const [m, setM] = useState<MapView | null>(null)
  const [pick, setPick] = useState<string | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    fetch(`/api/map/${encodeURIComponent(id)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then(setM)
      .catch(() => setM(null))
  }, [id, version])

  if (!m) return <p className="text-[var(--dim)]">No map yet.</p>
  if (!m.places.length) return <p className="text-[var(--dim)]">No known places yet.</p>

  const xs = m.places.map((p) => p.at[0])
  const ys = m.places.map((p) => p.at[1])
  const minX = Math.min(...xs)
  const minY = Math.min(...ys)
  const width = (Math.max(...xs) - minX) * GAP + 160
  const height = (Math.max(...ys) - minY) * GAP + 110
  const pt = (at: [number, number]) => [(at[0] - minX) * GAP + 80, (at[1] - minY) * GAP + 50]
  const byId = Object.fromEntries(m.places.map((p) => [p.id, p]))
  const target = pick ? byId[pick] : null

  const travel = async () => {
    if (!pick) return
    const res = await postJson('/api/map/travel', { map: id, to: pick })
    if (res.ok) onTravel()
    else setError((await res.json()).error ?? 'The DM cannot take that now.')
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="overflow-auto">
        <svg width={width} height={height} className="max-w-none" role="img" aria-label={`Map of ${m.name}`}>
          {m.routes.map((r) => {
            const [x1, y1] = pt(byId[r.a].at)
            const [x2, y2] = pt(byId[r.b].at)
            return (
              <g key={`${r.a}-${r.b}`}>
                <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#8a8299" strokeWidth={3} strokeDasharray="6 6" />
                {r.travel && (
                  <text x={(x1 + x2) / 2 + 6} y={(y1 + y2) / 2 - 6} fill="#c9a96e" fontSize={16} stroke="#14121c" strokeWidth={4} paintOrder="stroke">
                    {r.travel}
                  </text>
                )}
              </g>
            )
          })}
          {m.places.map((p) => {
            const [x, y] = pt(p.at)
            const here = p.id === m.here
            return (
              <g
                key={p.id}
                role="button"
                tabIndex={here ? -1 : 0}
                aria-label={here ? `${p.name} (you are here)` : `Travel to ${p.name}`}
                onClick={() => !here && setPick(p.id)}
                onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && !here && setPick(p.id)}
                className={here ? '' : 'cursor-pointer'}
                opacity={p.visited || here ? 1 : 0.6}
              >
                <rect x={x - 22} y={y - 22} width={44} height={44} fill="#1f1b2b" stroke={here ? '#55ff33' : pick === p.id ? '#e07a3f' : '#c9a96e'} strokeWidth={here || pick === p.id ? 3 : 2} />
                <image href={`/asset/icon/${p.icon}.png`} x={x - 16} y={y - 16} width={32} height={32} style={{ imageRendering: 'pixelated' }} />
                <text x={x} y={y + 40} textAnchor="middle" fill={here ? '#55ff33' : '#ece6d6'} fontSize={16} stroke="#14121c" strokeWidth={4} paintOrder="stroke">
                  {p.name}
                </text>
              </g>
            )
          })}
        </svg>
      </div>
      {target && (
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-lg">Travel to {target.name}?</span>
          <Button size="sm" disabled={!canAct || !m.here} onClick={travel} className="text-[10px]">
            Travel
          </Button>
          <Button size="sm" variant="outline" onClick={() => setPick(null)} className="text-[10px]">
            Cancel
          </Button>
          {!m.here && <span className="text-[var(--dim)]">You are not on this map.</span>}
          {!canAct && <span className="text-[var(--dim)]">Wait for the DM.</span>}
        </div>
      )}
      {error && <p role="alert" className="text-red-400">{error}</p>}
    </div>
  )
}

/** The current level of the world, and the levels above it. Looking costs no DM turn; only Travel does. */
export function MapOverlay({ open, onClose, state, canAct }: { open: boolean; onClose: () => void; state: StageState; canAct: boolean }) {
  const [levels, setLevels] = useState<Level[] | null>(null)
  const [index, setIndex] = useState(0)
  const where = `${state.explore}|${state.place?.place}`

  useEffect(() => {
    if (!open) return
    setIndex(0)
    fetch('/api/map')
      .then((r) => r.json())
      .then((d) => setLevels(d.levels))
      .catch(() => setLevels([]))
  }, [open, where])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null
  const level = levels?.[index]
  const version = level ? state.versions?.[`${level.kind}:${level.id}`] ?? 0 : 0

  return (
    <div className="fixed inset-0 z-40 grid place-items-center bg-black/70 p-4" onClick={onClose}>
      <section
        role="dialog"
        aria-label="Map"
        className="flex max-h-full w-full max-w-4xl flex-col gap-4 overflow-hidden border-4 border-[var(--gold)] bg-[var(--ink)] p-4"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex flex-wrap items-center gap-3">
          <h2 className="pixel-font text-xs text-[var(--gold)]">{level?.name ?? 'Map'}</h2>
          {index > 0 && (
            <Button size="sm" variant="outline" onClick={() => setIndex(index - 1)} className="text-[10px]">
              ▼ {levels![index - 1].name}
            </Button>
          )}
          {levels && index + 1 < levels.length && (
            <Button size="sm" variant="outline" onClick={() => setIndex(index + 1)} className="text-[10px]">
              ▲ {levels[index + 1].name}
            </Button>
          )}
          <button type="button" onClick={onClose} className="pixel-font ml-auto text-[10px] text-[var(--dim)] hover:text-[var(--parchment)]">
            Close ✕
          </button>
        </header>
        <div className="min-h-0 overflow-auto">
          {levels === null ? (
            <p className="text-[var(--dim)]">Unrolling the map…</p>
          ) : !level ? (
            <p className="text-lg text-[var(--dim)]">No map yet. Places appear here when the DM shows them to you.</p>
          ) : level.kind === 'site' ? (
            <SiteMap id={level.id} version={version} />
          ) : (
            <GraphMap id={level.id} version={version} canAct={canAct} onTravel={onClose} />
          )}
        </div>
      </section>
    </div>
  )
}
