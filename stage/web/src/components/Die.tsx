import { useEffect, useRef } from 'react'

import { reducedMotion } from '@/lib/prefs'
import { drawDie, FONT, randomSpin, restingPose, tumble, type Kind, type Tone } from '@/lib/dice'

// One roll, in time: the die tumbles and lands, stops for a moment, then its number grows.
export const ROLL_MS = 1150
export const PAUSE_MS = 250
export const GROW_MS = 300
/** From the first frame until the number has fully grown. `rate` (a prop) speeds it up: 2 is twice as fast. */
export const DIE_MS = ROLL_MS + PAUSE_MS + GROW_MS

/**
 * A die on a canvas (`kind`, a d20 by default). It tumbles to `face` and then grows `label` (default: the face) over itself.
 * `settled`: the roll is over, so show the end state now. It starts true for a die that does not roll, and the
 * window sets it when the player clicks to skip. `tone` is the colour the die takes when the number grows.
 */
export function Die({ face, label, kind = 'd20', tone = 'plain', settled, size, className = '', glow, rate = 1 }: { face: number | string; label?: string | number; kind?: Kind; tone?: Tone; settled: boolean; size: number; className?: string; glow?: string; rate?: number }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const live = useRef({ tone, label: String(label ?? face), settled, rate })
  const paint = useRef<() => void>(() => {})

  useEffect(() => {
    live.current = { tone, label: String(label ?? face), settled, rate }
  })

  useEffect(() => {
    const cv = canvas.current
    const ctx = cv?.getContext('2d')
    if (!cv || !ctx) return
    const res = Math.round(size * (window.devicePixelRatio || 1))
    cv.width = res; cv.height = res
    const spin = randomSpin()
    const start = performance.now()
    let raf = 0
    const frame = () => {
      const { tone, label, settled, rate } = live.current
      const ms = settled || reducedMotion() ? DIE_MS : (performance.now() - start) * rate
      const landed = ms >= ROLL_MS
      const grown = Math.max(0, Math.min(1, (ms - ROLL_MS - PAUSE_MS) / GROW_MS))
      const pose = landed ? restingPose(kind, String(face)) : tumble(kind, String(face), ms / ROLL_MS, spin)
      // The die takes its colour when the number appears.
      drawDie(ctx, res, kind, pose, grown > 0 ? tone : 'plain', grown > 0 ? { text: label, t: grown } : null, size <= 32 ? 1.6 : 1)
      return ms >= DIE_MS
    }
    const loop = () => { if (!frame()) raf = requestAnimationFrame(loop) }
    paint.current = () => { cancelAnimationFrame(raf); loop() }
    loop()
    // The pixel font may arrive after the first frame.
    document.fonts?.load(`20px ${FONT}`).then(() => paint.current()).catch(() => {})
    return () => cancelAnimationFrame(raf)
  }, [face, size, kind])

  // A change of colour, label or `settled` (a skip) shows at once, also after the animation has ended.
  useEffect(() => paint.current(), [tone, label, settled])

  return <canvas ref={canvas} aria-hidden="true" className={className} style={{ width: size, height: size, ...(glow ? ({ '--glow': glow } as React.CSSProperties) : {}) }} />
}
