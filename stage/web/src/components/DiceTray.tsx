import { useEffect, useLayoutEffect, useMemo, useRef, useState, type MutableRefObject } from 'react'

import { Button } from '@/components/ui/8bit/button'
import { drawDie, FONT, poseAt, randomSpin, restingPose, TONES, type Kind, type Tone } from '@/lib/dice'
import { timeScale, usePrefs } from '@/lib/prefs'
import { HZ, hopAt, rng, simulate, turnLeft, type Throw } from '@/lib/traySim'

// The damage tray. Before the throw, each roll has its own row (a damage type, with its dice). The rows dissolve and
// all the dice are thrown into one box: they bounce off the walls and off each other, and each stops where its
// path ends. The server has already decided every number. The throw is only for show.
const WAIT_MS = 1000 // before an automatic throw
const DISSOLVE_MS = 350
const NUMBER_PAUSE = 0.25 // s after a die stops, before its number grows
const NUMBER_GROW = 0.3
const AFTER = 0.6 // s from the last stop to "done"

export interface TrayRow {
  label: string
  expr: string
  tone: Tone
  dice: { kind: Kind; label: string }[]
  total: number
}

const dieSize = (n: number) => (n <= 4 ? 56 : n <= 8 ? 44 : n <= 12 ? 36 : 28)
const clamp01 = (x: number) => Math.max(0, Math.min(1, x))
const LABEL_H = 22

/** The rows, one above the other, each with its dice in a line (more lines when they do not fit). */
function layout(rows: TrayRow[], size: number, width: number) {
  const pad = 8, gap = 6, perLine = Math.max(1, Math.floor((width - 2 * pad + gap) / (size + gap)))
  let y = pad
  const starts: { x: number; y: number }[] = [], labels: number[] = []
  for (const row of rows) {
    labels.push(y)
    const lines = Math.ceil(row.dice.length / perLine)
    row.dice.forEach((_, i) => starts.push({ x: pad + size / 2 + (i % perLine) * (size + gap), y: y + LABEL_H + size / 2 + Math.floor(i / perLine) * (size + 4) }))
    y += LABEL_H + lines * (size + 4) + 8
  }
  return { starts, labels, height: y }
}

type Phase = 'rows' | 'throw' | 'done'

/**
 * `queued`: another roll waits behind this one, so the dice are thrown at once. Otherwise they wait a second or for a click, as the
 * player chose. `skipRef` is filled with a function that a click on the window calls: it throws (before the throw) or lands the dice
 * (during it) and returns true; once the tray is done it returns false.
 */
export function DiceTray({ rows, crit, seed, queued, onSettled, skipRef }: {
  rows: TrayRow[]
  crit: boolean
  seed: number
  queued: boolean
  onSettled: () => void
  skipRef: MutableRefObject<(() => boolean) | null>
}) {
  const prefs = usePrefs()
  const tm = timeScale(prefs)
  const wait = queued ? 'now' : prefs.throw
  const box = useRef<HTMLDivElement>(null)
  const canvases = useRef<(HTMLCanvasElement | null)[]>([])
  const contexts = useRef<(CanvasRenderingContext2D | null)[]>([])
  const frozen = useRef<boolean[]>([]) // dice that have landed and show their number: no more redraws
  const [width, setWidth] = useState(0)
  const [phase, setPhase] = useState<Phase>(tm ? 'rows' : 'done')
  const phaseRef = useRef(phase)
  const goTo = (p: Phase) => { phaseRef.current = p; setPhase(p) }
  const sim = useRef<Throw | null>(null)
  const skipped = useRef(false)
  const repaint = useRef<() => void>(() => {})
  const settled = useRef(onSettled)
  useEffect(() => { settled.current = onSettled })

  useLayoutEffect(() => setWidth(box.current?.clientWidth || 360), [])

  const dice = useMemo(() => rows.flatMap((row) => row.dice.map((d) => ({ ...d, tone: row.tone }))), [rows])
  const spins = useMemo(() => {
    const rand = rng(seed ^ 0x9e3779b9) // the same tumble on every screen
    return dice.map(() => randomSpin(rand))
  }, [dice, seed])
  const geo = useMemo(() => {
    if (!width) return null
    const size = width < 300 && dice.length > 8 ? 28 : dieSize(dice.length), r = 0.42 * size
    const lay = layout(rows, size, width)
    const height = Math.ceil(Math.max(lay.height + 4, 130, (dice.length * Math.PI * r * r) / 0.28 / width))
    return { ...lay, size, r, height }
  }, [width, rows, dice.length])
  const res = geo ? Math.round(geo.size * (window.devicePixelRatio || 1)) : 0

  // Draw a frame of the throw (or, before it, the dice in their rows).
  const paint = (f: number, elapsed: number, force = false) => {
    if (!geo) return
    if (force) frozen.current = []
    const t = sim.current
    dice.forEach((d, i) => {
      if (frozen.current[i]) return
      const cv = canvases.current[i], ctx = (contexts.current[i] ??= cv?.getContext('2d') ?? null)
      if (!cv || !ctx) return
      const at = t ? { x: t.frames[(f * t.n + i) * 2], y: t.frames[(f * t.n + i) * 2 + 1] } : geo.starts[i]
      cv.style.transform = `translate(${at.x - geo.size / 2}px, ${at.y - geo.size / 2}px)`
      cv.style.zIndex = String(1 + Math.round(at.y))
      const k = t ? turnLeft(t, i, f) : 1
      const grow = t ? clamp01((elapsed - t.stop[i] - NUMBER_PAUSE) / NUMBER_GROW) : 0
      const pose = grow >= 1 ? restingPose(d.kind, d.label) : poseAt(d.kind, d.label, k, spins[i], t ? hopAt(t, i, Math.min(elapsed, t.end)) : 0)
      drawDie(ctx, res, d.kind, pose, d.tone, grow > 0 ? { text: d.label, t: grow } : null, geo.size <= 32 ? 1.6 : 1)
      if (grow >= 1) frozen.current[i] = true
    })
  }
  const run = () => {
    if (geo) sim.current = simulate(geo.starts, geo.r, width, geo.height, seed)
  }

  useEffect(() => {
    if (!geo) return
    let dead = false, raf = 0
    const timers: number[] = []
    const later = (fn: () => void, ms: number) => timers.push(window.setTimeout(fn, ms))
    if (phase === 'rows') {
      sim.current = null
      repaint.current = () => paint(0, 0, true)
      repaint.current()
      if (wait === 'now') later(() => goTo('throw'), 0)
      else if (wait === 'auto') later(() => goTo('throw'), WAIT_MS * tm)
    } else if (phase === 'throw') {
      run()
      frozen.current = []
      const t = sim.current!
      repaint.current = () => paint(t.N, 99, true)
      const start = performance.now() + (wait === 'now' ? 0 : DISSOLVE_MS) * tm // a queued roll skips the dissolve
      const frame = () => {
        if (dead) return
        const elapsed = skipped.current ? 99 : Math.max(0, ((performance.now() - start) / 1000) / tm)
        paint(Math.min(t.N, Math.floor(elapsed * HZ)), elapsed)
        if (elapsed >= t.end + AFTER) goTo('done')
        else raf = requestAnimationFrame(frame)
      }
      frame()
    } else {
      if (!sim.current) run()
      repaint.current = () => paint(sim.current!.N, 99, true)
      repaint.current()
      settled.current()
    }
    return () => {
      dead = true
      cancelAnimationFrame(raf)
      timers.forEach(clearTimeout)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, geo])

  // Another roll is queued behind this one: no more waiting.
  useEffect(() => {
    if (wait === 'now' && phaseRef.current === 'rows') goTo('throw')
  }, [wait])

  // The pixel font may arrive after the first frame.
  useEffect(() => { document.fonts?.load(`20px ${FONT}`).then(() => repaint.current()).catch(() => {}) }, [])

  useEffect(() => {
    skipRef.current = () => {
      if (phaseRef.current === 'rows') { goTo('throw'); return true }
      if (phaseRef.current === 'throw') { skipped.current = true; return true }
      return false
    }
    return () => { skipRef.current = null }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [skipRef])

  let at = 0
  return (
    <div className="flex w-full flex-col gap-2 border-2 border-[var(--border)] bg-[var(--panel-2)] p-2">
      <div ref={box} className="relative w-full overflow-hidden" style={{ height: geo?.height ?? 130 }}>
        {geo &&
          rows.map((row, ri) => (
            <div
              key={`label-${ri}`}
              className={`absolute right-2 left-2 truncate border-l-4 pl-2 text-base leading-[20px] transition-opacity duration-300 ease-[steps(5)] ${phase === 'rows' ? '' : 'opacity-0'}`}
              style={{ top: geo.labels[ri], borderColor: TONES[row.tone].ramp[2] }}
            >
              <span className="capitalize">{row.label}</span> <span className="text-sm text-[var(--dim)]">{row.expr}</span>
            </div>
          ))}
        {geo &&
          rows.map((row) =>
            row.dice.map((_, di) => {
              const i = at++
              return (
                <canvas
                  key={`die-${i}-${di}`}
                  ref={(el) => void (canvases.current[i] = el)}
                  aria-hidden="true"
                  width={res}
                  height={res}
                  className={`absolute top-0 left-0 ${crit ? 'die-crit' : ''}`}
                  style={{ width: geo.size, height: geo.size }}
                />
              )
            }),
          )}
      </div>
      <div className="flex min-h-8 flex-wrap items-center gap-2">
        {phase === 'rows' ? (
          <>
            <Button size="sm" className="text-[10px]" onClick={(e) => { e.stopPropagation(); skipRef.current?.() }}>
              Throw
            </Button>
            {wait === 'auto' && <span className="text-sm text-[var(--dim)]">Throwing in a second</span>}
          </>
        ) : (
          <>
            {rows.map((row, i) => (
              <span key={i} className={`border-2 px-2 text-base ${phase === 'done' ? 'tile-in' : 'invisible'}`} style={{ borderColor: TONES[row.tone].ramp[2] }}>
                <span className="capitalize">{row.label}</span> <span className="pixel-font ml-1 text-xs text-[var(--ember)]">{row.total}</span>
              </span>
            ))}
            {rows.length > 1 && (
              <span className={`ml-auto border-2 border-[var(--gold)] px-2 text-base ${phase === 'done' ? 'tile-in' : 'invisible'}`}>
                Total <span className="pixel-font ml-1 text-xs text-[var(--ember)]">{rows.reduce((n, r) => n + r.total, 0)}</span>
              </span>
            )}
          </>
        )}
      </div>
    </div>
  )
}
