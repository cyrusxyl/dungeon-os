// A 3D d20 drawn on a canvas: no library. The die comes from real icosahedron coordinates, so every face is flat and
// the roll can end with any face toward the camera. Flat shading, light from the top left.

type V3 = [number, number, number]
type Mat = number[] // 3x3, row major

const PHI = (1 + Math.sqrt(5)) / 2
const add = (a: V3, b: V3): V3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]]
const sub = (a: V3, b: V3): V3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
const mul = (a: V3, s: number): V3 => [a[0] * s, a[1] * s, a[2] * s]
const dot = (a: V3, b: V3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
const cross = (a: V3, b: V3): V3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
const norm = (a: V3) => mul(a, 1 / Math.hypot(...a))
const mean = (ps: V3[]) => mul(ps.reduce(add), 1 / ps.length)
const apply = (M: Mat, v: V3): V3 => [M[0] * v[0] + M[1] * v[1] + M[2] * v[2], M[3] * v[0] + M[4] * v[1] + M[5] * v[2], M[6] * v[0] + M[7] * v[1] + M[8] * v[2]]
const compose = (A: Mat, B: Mat): Mat => {
  const R: number[] = []
  for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) R.push(A[i * 3] * B[j] + A[i * 3 + 1] * B[3 + j] + A[i * 3 + 2] * B[6 + j])
  return R
}
function rotation(axis: V3, angle: number): Mat {
  const [x, y, z] = norm(axis)
  const c = Math.cos(angle), s = Math.sin(angle), t = 1 - c
  return [t * x * x + c, t * x * y - s * z, t * x * z + s * y, t * x * y + s * z, t * y * y + c, t * y * z - s * x, t * x * z - s * y, t * y * z + s * x, t * z * z + c]
}

type Face = { idx: number[]; n: V3; c: V3; up: V3; inr: number; label: number }

/** The 12 vertices and 20 triangles of an icosahedron, scaled to radius 1. Opposite faces add to 21. */
function build(): { verts: V3[]; faces: Face[] } {
  const verts: V3[] = []
  for (const [a, b, c] of [[0, 1, PHI], [PHI, 0, 1], [1, PHI, 0]])
    for (const sa of [1, -1]) for (const sb of [1, -1]) for (const sc of [1, -1]) {
      const p: V3 = [a * sa, b * sb, c * sc]
      if (!verts.some((q) => q.every((x, k) => Math.abs(x - p[k]) < 1e-6))) verts.push(p)
    }
  const r = Math.hypot(...verts[0])
  const unit = verts.map((v) => mul(v, 1 / r))
  const faces: Face[] = []
  const edge = (a: number, b: number) => Math.abs(Math.hypot(...sub(verts[a], verts[b])) - 2) < 1e-6
  for (let i = 0; i < 12; i++) for (let j = i + 1; j < 12; j++) for (let k = j + 1; k < 12; k++) {
    if (!(edge(i, j) && edge(j, k) && edge(i, k))) continue
    const c = mean([unit[i], unit[j], unit[k]])
    const n = norm(c)
    const up = norm(sub(unit[i], c))
    const inr = Math.hypot(...sub(c, mul(add(unit[i], unit[j]), 0.5)))
    faces.push({ idx: [i, j, k], n, c, up, inr, label: 0 })
  }
  // Number the faces: each face and the one opposite it add to 21.
  const used = new Set<number>()
  let low = 1
  faces.forEach((f, i) => {
    if (used.has(i)) return
    const j = faces.findIndex((g) => dot(g.n, f.n) < -0.99)
    f.label = low
    faces[j].label = 21 - low
    used.add(i); used.add(j)
    low++
  })
  return { verts: unit, faces }
}
const DIE = build()

/** The turn that puts the face with this number toward the camera, its number upright. */
function toFace(face: number): Mat {
  const f = DIE.faces.find((g) => g.label === face) ?? DIE.faces[0]
  const u = cross(f.up, f.n)
  return [...u, ...f.up, ...f.n]
}
// A small tilt so a resting die still shows some depth. It is too small to turn a neighbour face toward the camera.
const TILT = compose(rotation([1, 0, 0], 0.16), rotation([0, 1, 0], 0.12))
const restPose = (face: number) => compose(TILT, toFace(face))

export type Tone = 'plain' | 'gold' | 'red'
const RAMP: Record<Tone, string[]> = {
  plain: ['#26213a', '#3a3350', '#4b4366', '#5e5580'],
  gold: ['#8a7143', '#a88c57', '#c9a96e', '#e2c88f'],
  red: ['#6e2626', '#8a3030', '#a33a3a', '#c55353'],
}
const INK: Record<Tone, string> = { plain: '#ece6d6', gold: '#14121c', red: '#ece6d6' }
const OUTLINE = '#14121c'
const LIGHT = norm([-0.35, 0.55, 0.75])
const rgb = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16))
function shade(tone: Tone, t: number): string {
  const r = RAMP[tone]
  const x = t * 3, i = Math.min(2, Math.floor(x)), f = x - i
  const a = rgb(r[i]), b = rgb(r[i + 1])
  return `rgb(${a.map((p, k) => Math.round(p + (b[k] - p) * f)).join(',')})`
}

export const FONT = '"Press Start 2P", "Pixel Digits", monospace'

export type Pose = { M: Mat; hop: number; rest?: boolean }
/** Spin about two fixed axes that slow down to zero, so the die ends exactly on `face`. `t`: 0 to 1. */
export function tumble(face: number, t: number, spin: { a1: V3; a2: V3; w1: number; w2: number }): Pose {
  const k = Math.pow(1 - t, 3)
  const M = compose(TILT, compose(rotation(spin.a1, spin.w1 * k), compose(rotation(spin.a2, spin.w2 * k), toFace(face))))
  return { M, hop: Math.abs(Math.sin(t * Math.PI * 3)) * (1 - t) * (1 - t) * 0.04 }
}
export function randomSpin() {
  const r = () => Math.random() - 0.5
  return { a1: norm([r(), r(), r() + 0.01]), a2: norm([r(), 1, r()]), w1: (5 + Math.random() * 2) * Math.PI, w2: (3 + Math.random() * 2) * Math.PI }
}
export const restingPose = (face: number): Pose => ({ M: restPose(face), hop: 0, rest: true })

/**
 * Draw the die. `size`: canvas pixels. `big`: the final number, drawn over the die and past its edge; it grows with
 * `bigT` (0 to 1, with a small overshoot). Without it, the faces carry their own numbers.
 */
export function drawDie(ctx: CanvasRenderingContext2D, size: number, pose: Pose, tone: Tone, big: { text: string; t: number } | null) {
  ctx.setTransform(1, 0, 0, 1, 0, 0)
  ctx.clearRect(0, 0, size, size)
  const S = size * 0.4, cx = size / 2, cy = size * 0.5 - pose.hop * size
  const shadow = 1 - pose.hop * 4
  ctx.fillStyle = 'rgba(0,0,0,.35)'
  ctx.beginPath(); ctx.ellipse(cx, size * 0.9, size * 0.3 * shadow, size * 0.045 * shadow, 0, 0, 7); ctx.fill()
  const P = DIE.verts.map((v) => apply(pose.M, v))
  ctx.lineJoin = 'round'; ctx.lineCap = 'round'
  for (const f of DIE.faces) {
    const n = apply(pose.M, f.n)
    if (n[2] <= 0) continue
    ctx.beginPath()
    f.idx.forEach((i, k) => (k ? ctx.lineTo(cx + S * P[i][0], cy - S * P[i][1]) : ctx.moveTo(cx + S * P[i][0], cy - S * P[i][1])))
    ctx.closePath()
    ctx.fillStyle = shade(tone, Math.max(0, Math.min(1, dot(n, LIGHT) / 0.85)))
    ctx.fill()
    ctx.strokeStyle = OUTLINE; ctx.lineWidth = Math.max(1.2, size / 40); ctx.stroke()
    // A die at rest shows only the face that looks at us; a tumbling die shows every face it turns to the camera.
    if (big || n[2] < (pose.rest ? 0.9 : 0.4)) continue
    // The number lies in the face plane: its axes are the face's "right" and "up", turned by the pose.
    const q = apply(pose.M, add(f.c, mul(f.up, -f.inr * 0.1)))
    const up = apply(pose.M, f.up), right = apply(pose.M, cross(f.up, f.n))
    const k = (S * f.inr * (f.label > 9 ? 0.85 : 1.1)) / 20
    ctx.save()
    ctx.transform(k * right[0], -k * right[1], -k * up[0], k * up[1], cx + S * q[0], cy - S * q[1])
    ctx.font = `20px ${FONT}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
    ctx.fillStyle = INK[tone]; ctx.fillText(String(f.label), 0, 0)
    ctx.restore()
  }
  if (big) {
    const x = big.t, grow = 1 + 2.70158 * (x - 1) ** 3 + 1.70158 * (x - 1) ** 2
    // One size for every die; three digits shrink to fit.
    const em = size * 0.3 * grow * (big.text.length > 2 ? 2 / big.text.length : 1)
    ctx.font = `${em}px ${FONT}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
    ctx.lineJoin = 'round'; ctx.lineWidth = Math.max(2, em * 0.2)
    ctx.strokeStyle = tone === 'gold' ? '#e2c88f' : OUTLINE; ctx.strokeText(big.text, cx, cy)
    ctx.fillStyle = INK[tone]; ctx.fillText(big.text, cx, cy)
  }
}

/** Which number points at the camera under `pose`. Used by tests. */
export function facing(pose: Pose): number {
  let best = 0, bz = -9
  for (const f of DIE.faces) { const z = apply(pose.M, f.n)[2]; if (z > bz) { bz = z; best = f.label } }
  return best
}
