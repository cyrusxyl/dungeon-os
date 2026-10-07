import { useEffect, useRef } from 'react'

import { drawDie, FONT, randomSpin, restingPose, tumble, type Tone } from '@/lib/d20'

// One roll, in time: the die tumbles and lands, stops for a moment, then its number grows.
export const ROLL_MS = 1150
export const PAUSE_MS = 250
export const GROW_MS = 300
/** From the first frame until the number has fully grown. */
export const DIE_MS = ROLL_MS + PAUSE_MS + GROW_MS

const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

/**
 * A d20 on a canvas. It tumbles to `face` and then grows `label` (default: the face) over itself.
 * `settled`: the roll is over, so show the end state now. It starts true for a die that does not roll, and the
 * window sets it when the player clicks to skip. `tone` is the colour the die takes when the number grows.
 */
export function Die({ face, label, tone = 'plain', settled, size, className = '', glow }: { face: number; label?: string | number; tone?: Tone; settled: boolean; size: number; className?: string; glow?: string }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const live = useRef({ tone, label: String(label ?? face), settled })
  const paint = useRef<() => void>(() => {})

  useEffect(() => {
    live.current = { tone, label: String(label ?? face), settled }
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
      const { tone, label, settled } = live.current
      const ms = settled || reducedMotion() ? DIE_MS : performance.now() - start
      const landed = ms >= ROLL_MS
      const grown = Math.max(0, Math.min(1, (ms - ROLL_MS - PAUSE_MS) / GROW_MS))
      const pose = landed ? restingPose(face) : tumble(face, ms / ROLL_MS, spin)
      // The die takes its colour when the number appears.
      drawDie(ctx, res, pose, grown > 0 ? tone : 'plain', grown > 0 ? { text: label, t: grown } : null)
      return ms >= DIE_MS
    }
    const loop = () => { if (!frame()) raf = requestAnimationFrame(loop) }
    paint.current = () => { cancelAnimationFrame(raf); loop() }
    loop()
    // The pixel font may arrive after the first frame.
    document.fonts?.load(`20px ${FONT}`).then(() => paint.current()).catch(() => {})
    return () => cancelAnimationFrame(raf)
  }, [face, size])

  // A change of colour, label or `settled` (a skip) shows at once, also after the animation has ended.
  useEffect(() => paint.current(), [tone, label, settled])

  return <canvas ref={canvas} aria-hidden="true" className={className} style={{ width: size, height: size, ...(glow ? ({ '--glow': glow } as React.CSSProperties) : {}) }} />
}
