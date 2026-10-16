// The dice throw, as billiards: equal discs, perfect collisions, perfect walls, constant slow-down.
// It runs the whole throw first, at a fixed step, and playback picks a frame by time. The server has already
// decided every number, so this is only for show. One die alone has L = v² / 2a and T = v / a. With collisions the
// dice pass speed to each other, so the run gives each die its real path length and stop time.

export const HZ = 240
const DT = 1 / HZ

interface Start { x: number; y: number }
export interface Throw {
  n: number
  /** Last frame index. */
  N: number
  /** Disc centres: frame f, die i at [(f * n + i) * 2] and the next. */
  frames: Float32Array
  /** Distance each die has moved, by frame: [f * n + i]. */
  S: Float32Array
  /** Total path of each die. */
  L: number[]
  /** When each die last moved, in seconds. */
  stop: number[]
  /** When the whole throw ends, in seconds. */
  end: number
  /** Launch and hard hits of each die, in seconds. */
  ev: number[][]
}

/** A small seeded generator, so two screens can show the same throw. */
export function rng(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const TIME = 1.0 // about when the dice stop, in seconds
const REACH = 1.5 // the path of a die, in box widths

/** `starts`: where each die begins (centres). `r`: disc radius. `W`, `H`: the box. */
export function simulate(starts: Start[], r: number, W: number, H: number, seed = 1): Throw {
  const n = starts.length, rand = rng(seed), T = TIME
  const v0 = (2 * REACH * W) / T, a = v0 / T, cap = Math.ceil((2 * T + 0.3) * HZ)
  const x = Float64Array.from(starts, (p) => p.x), y = Float64Array.from(starts, (p) => p.y), px = new Float64Array(n), py = new Float64Array(n)
  const vx = new Array<number>(n).fill(0), vy = new Array<number>(n).fill(0)
  const launched = new Array<boolean>(n).fill(false), last = new Array<number>(n).fill(0), s = new Array<number>(n).fill(0)
  const ev: number[][] = starts.map(() => []), delay: number[] = [], speed: number[] = [], dir: number[] = []
  for (let i = 0; i < n; i++) {
    delay.push(rand() * 0.15)
    speed.push(v0 * (0.75 + rand() * 0.4))
    const tx = r + rand() * (W - 2 * r), ty = r + rand() * (H - 2 * r)
    dir.push(Math.atan2(ty - y[i], tx - x[i]) + (rand() - 0.5) * 0.5)
  }
  const frames = new Float32Array((cap + 1) * n * 2), S = new Float32Array((cap + 1) * n)
  const save = (k: number) => {
    for (let i = 0; i < n; i++) { frames[(k * n + i) * 2] = x[i]; frames[(k * n + i) * 2 + 1] = y[i]; S[k * n + i] = s[i] }
  }
  save(0)
  let N = 0
  for (let k = 1; k <= cap; k++) {
    const t = k * DT
    px.set(x); py.set(y)
    let moving = false
    for (let i = 0; i < n; i++) {
      if (!launched[i]) {
        if (t < delay[i]) { moving = true; continue }
        launched[i] = true; vx[i] = Math.cos(dir[i]) * speed[i]; vy[i] = Math.sin(dir[i]) * speed[i]; ev[i].push(t)
      }
      x[i] += vx[i] * DT; y[i] += vy[i] * DT
      if (x[i] < r) { x[i] = r; if (vx[i] < 0) { if (-vx[i] > 40) ev[i].push(t); vx[i] = -vx[i] } }
      if (x[i] > W - r) { x[i] = W - r; if (vx[i] > 0) { if (vx[i] > 40) ev[i].push(t); vx[i] = -vx[i] } }
      if (y[i] < r) { y[i] = r; if (vy[i] < 0) { if (-vy[i] > 40) ev[i].push(t); vy[i] = -vy[i] } }
      if (y[i] > H - r) { y[i] = H - r; if (vy[i] > 0) { if (vy[i] > 40) ev[i].push(t); vy[i] = -vy[i] } }
      const sp = Math.hypot(vx[i], vy[i])
      if (sp > 0) {
        const ns = sp - a * DT
        if (ns <= 0) { vx[i] = 0; vy[i] = 0 } else { vx[i] *= ns / sp; vy[i] *= ns / sp }
      }
    }
    for (let pass = 0; pass < 2; pass++)
      for (let i = 0; i < n; i++) {
        if (!launched[i]) continue
        for (let j = i + 1; j < n; j++) {
          if (!launched[j] || (!vx[i] && !vy[i] && !vx[j] && !vy[j])) continue // two dice at rest stay apart
          const dx = x[i] - x[j], dy = y[i] - y[j], d2 = dx * dx + dy * dy
          if (d2 >= 4 * r * r) continue
          const d = Math.sqrt(d2) || 1e-6, nx = dx / d, ny = dy / d
          const vn = (vx[i] - vx[j]) * nx + (vy[i] - vy[j]) * ny
          if (vn < 0) {
            // Approaching: equal masses swap the parts of their speed along the line between them.
            vx[i] -= vn * nx; vy[i] -= vn * ny; vx[j] += vn * nx; vy[j] += vn * ny
            if (pass === 0 && -vn > 40) { ev[i].push(t); ev[j].push(t) }
          }
          const push = (2 * r - d) / 2
          x[i] += nx * push; y[i] += ny * push; x[j] -= nx * push; y[j] -= ny * push
        }
      }
    for (let i = 0; i < n; i++) {
      x[i] = Math.min(W - r, Math.max(r, x[i])); y[i] = Math.min(H - r, Math.max(r, y[i]))
      const dp = Math.hypot(x[i] - px[i], y[i] - py[i])
      s[i] += dp
      if (dp > 0.01 || vx[i] || vy[i]) { moving = true; last[i] = k }
    }
    save(k); N = k
    if (!moving) break
    if (k === cap) { vx.fill(0); vy.fill(0) } // a hard stop
  }
  const total = S.subarray(0, (N + 1) * n)
  return { n, N, frames: frames.subarray(0, (N + 1) * n * 2), S: total, L: Array.from({ length: n }, (_, i) => total[N * n + i]), stop: last.map((k) => k * DT), end: N * DT, ev }
}

/** The turn a die has left at frame f: 1 at the start, 0 when its path is done. */
export const turnLeft = (t: Throw, i: number, f: number): number => (t.L[i] > 0 ? Math.max(0, 1 - t.S[f * t.n + i] / t.L[i]) : 0)

/** A short hop (0 to 0.05 of the die size) from the launch and from each hard hit. */
export function hopAt(t: Throw, i: number, seconds: number): number {
  let h = 0
  for (const e of t.ev[i]) {
    const u = (seconds - e) / 0.16
    if (u >= 0 && u < 1) h = Math.max(h, Math.sin(Math.PI * u))
  }
  return h * 0.05
}
