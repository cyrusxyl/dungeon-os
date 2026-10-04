import { useEffect, useRef, useState } from 'react'

import type { Roll } from '@/lib/stage'

const SHUFFLE_MS = 700
const SHOW_MS = 4000

/** A pixel d20 that tumbles, then lands on the roll's total. */
export function DiceOverlay({ roll }: { roll: Roll | null }) {
  // Rolls already on record when the page loads are history, not news.
  const firstSeq = useRef(roll?.seq ?? 0)
  const [shown, setShown] = useState<Roll | null>(null)
  const [face, setFace] = useState(0)
  const [settled, setSettled] = useState(false)

  useEffect(() => {
    if (!roll || roll.seq <= firstSeq.current) return
    setShown(roll)
    setSettled(false)
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const start = performance.now()
    let frame = 0
    const tick = (now: number) => {
      if (reduced || now - start > SHUFFLE_MS) {
        setFace(roll.total)
        setSettled(true)
        return
      }
      setFace(1 + Math.floor(Math.random() * 20))
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    const hide = window.setTimeout(() => setShown(null), SHOW_MS)
    return () => {
      cancelAnimationFrame(frame)
      window.clearTimeout(hide)
    }
  }, [roll])

  if (!shown) return null
  const d20 = shown.dice.find((d) => d.die.endsWith('d20') && d.faces.length === 1)?.faces[0]
  const crit = settled && d20 === 20
  const fumble = settled && d20 === 1
  const color = crit ? 'var(--gold)' : fumble ? '#e05050' : 'var(--parchment)'

  return (
    <div className="dice-pop pointer-events-none absolute top-3 right-3 z-20 flex items-center gap-3 border-4 border-[var(--gold)] bg-[var(--panel)]/95 px-3 py-2" role="status" aria-live="polite">
      <svg viewBox="0 0 16 16" className={`pixelated size-12 ${settled ? '' : 'animate-spin'}`} shapeRendering="crispEdges" aria-hidden="true">
        <polygon points="8,0 15,4 15,12 8,16 1,12 1,4" fill={color} />
        <polygon points="8,3 12,10 4,10" fill="var(--ink)" />
      </svg>
      <div className="flex flex-col">
        <span className="pixel-font text-2xl tabular-nums" style={{ color }}>
          {face}
        </span>
        <span className="text-sm text-[var(--dim)]">
          {shown.expr}
          {settled && shown.dice.length > 0 && ` · ${shown.dice.map((d) => `[${d.faces.join(', ')}]`).join(' ')}`}
          {crit && ' · critical!'}
          {fumble && ' · fumble'}
        </span>
      </div>
    </div>
  )
}
