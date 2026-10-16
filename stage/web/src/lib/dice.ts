// 3D dice drawn on a canvas: no library. Each solid comes from real coordinates, so every face is flat and a roll
// can end with any face toward the camera. Flat shading, light from the top left. A d4 is read at the vertex that
// points at the camera; every other die at its front face. The d100 is two d10 (tens and units).

type V3 = [number, number, number]
type Mat = number[] // 3x3, row major

const PHI = (1 + Math.sqrt(5)) / 2
const add = (a: V3, b: V3): V3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]]
const sub = (a: V3, b: V3): V3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
const mul = (a: V3, s: number): V3 => [a[0] * s, a[1] * s, a[2] * s]
const dot = (a: V3, b: V3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
const cross = (a: V3, b: V3): V3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
const len = (a: V3) => Math.hypot(a[0], a[1], a[2])
const norm = (a: V3) => mul(a, 1 / len(a))
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

/** The solids. `d10t` is the tens die of a d100 (labels 00 to 90). */
export type Kind = 'd4' | 'd6' | 'd8' | 'd10' | 'd10t' | 'd12' | 'd20'
interface Face { idx: number[]; n: V3; c: V3; inr: number; up: V3; label: string; vlabels?: string[] }
interface Solid { key: Kind; verts: V3[]; faces: Face[]; fit: number; d4?: boolean }

/** Order a face's corners, find its normal, its inner radius and the "up" of its number. */
function finishFace(verts: V3[], idx: number[], upMode: 'edge' | 'vertex', apex?: number): Face {
  const c = mean(idx.map((i) => verts[i]))
  const e1 = norm(sub(verts[idx[0]], c)), ax = norm(c)
  const e2 = cross(ax, e1), e1b = cross(e2, ax)
  const ang = (i: number) => { const d = sub(verts[i], c); return Math.atan2(dot(d, e2), dot(d, e1b)) }
  idx = idx.slice().sort((a, b) => ang(a) - ang(b))
  let n = norm(cross(sub(verts[idx[1]], verts[idx[0]]), sub(verts[idx[2]], verts[idx[0]])))
  if (dot(n, c) < 0) n = mul(n, -1)
  let inr = Infinity
  for (let k = 0; k < idx.length; k++) {
    const a = verts[idx[k]], b = verts[idx[(k + 1) % idx.length]]
    inr = Math.min(inr, len(cross(sub(b, a), sub(c, a))) / len(sub(b, a)))
  }
  let up = upMode === 'edge' ? norm(sub(mul(add(verts[idx[0]], verts[idx[1]]), 0.5), c)) : norm(sub(verts[apex ?? idx[0]], c))
  up = norm(sub(up, mul(n, dot(up, n))))
  return { idx, n, c, inr, up, label: '' }
}
function solid(key: Kind, verts: V3[], faceSets: { idx: number[]; apex?: number }[], upMode: 'edge' | 'vertex', fit: number, d4 = false): Solid {
  const r = Math.max(...verts.map(len))
  const unit = verts.map((v) => mul(v, 1 / r))
  return { key, verts: unit, faces: faceSets.map((fs) => finishFace(unit, fs.idx, upMode, fs.apex)), fit, d4 }
}
/** The faces whose planes touch the corners that lie farthest along each normal. */
function fromNormals(verts: V3[], normals: V3[]): { idx: number[] }[] {
  return normals.map((n0) => {
    const n = norm(n0), m = Math.max(...verts.map((v) => dot(v, n)))
    return { idx: verts.map((v, i) => (dot(v, n) > m - 1e-4 ? i : -1)).filter((i) => i >= 0) }
  })
}
/** Number the faces so that each face and the one opposite add to the same total (labels low to high). */
function pairLabels(s: Solid, nums: string[]): Solid {
  const opp = (i: number) => {
    let best = 0, bd = 9
    s.faces.forEach((f, j) => { const d = dot(f.n, s.faces[i].n); if (d < bd) { bd = d; best = j } })
    return best
  }
  const done = new Set<number>(), left = nums.slice()
  s.faces.forEach((f, i) => {
    if (done.has(i)) return
    const j = opp(i)
    f.label = left.shift()!
    s.faces[j].label = left.pop()!
    done.add(i); done.add(j)
  })
  return s
}
const signs = (f: (x: number, y: number, z: number) => V3): V3[] => {
  const out: V3[] = []
  for (const sx of [1, -1]) for (const sy of [1, -1]) for (const sz of [1, -1]) out.push(f(sx, sy, sz))
  return out
}
const range = (n: number, from = 1) => Array.from({ length: n }, (_, i) => String(i + from))

function icosaVerts(): V3[] {
  const out: V3[] = []
  for (const [a, b, c] of [[0, 1, PHI], [PHI, 0, 1], [1, PHI, 0]])
    for (const sa of [1, -1]) for (const sb of [1, -1]) for (const sc of [1, -1]) {
      const p: V3 = [a * sa, b * sb, c * sc]
      if (!out.some((q) => q.every((x, k) => Math.abs(x - p[k]) < 1e-6))) out.push(p)
    }
  return out
}
function icosaFaces(v: V3[]): number[][] {
  const out: number[][] = []
  for (let i = 0; i < 12; i++) for (let j = i + 1; j < 12; j++) for (let k = j + 1; k < 12; k++)
    if ([[i, j], [j, k], [i, k]].every(([a, b]) => Math.abs(len(sub(v[a], v[b])) - 2) < 1e-6)) out.push([i, j, k])
  return out
}
function makeTetra(): Solid {
  const v: V3[] = [[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]]
  const s = solid('d4', v, fromNormals(v, v.map((p) => mul(p, -1))), 'vertex', 1.05, true)
  s.faces.forEach((f) => { f.vlabels = f.idx.map((i) => String(i + 1)) })
  return s
}
function makeTrap(tens: boolean): Solid {
  // A pentagonal trapezohedron. The apex height makes every kite flat.
  const eps = 0.12, d = Math.PI / 180, P: V3[] = [], Q: V3[] = []
  for (let k = 0; k < 5; k++) {
    P.push([Math.cos(72 * k * d), Math.sin(72 * k * d), eps])
    Q.push([Math.cos((72 * k + 36) * d), Math.sin((72 * k + 36) * d), -eps])
  }
  const n = cross(sub(P[1], P[0]), sub(Q[0], P[0]))
  const h = eps + n[0] / n[2]
  const v: V3[] = [[0, 0, h], [0, 0, -h], ...P, ...Q]
  const pi = (k: number) => 2 + (k % 5), qi = (k: number) => 7 + (k % 5)
  const sets: { idx: number[]; apex: number }[] = []
  for (let k = 0; k < 5; k++) sets.push({ idx: [0, pi(k), qi(k), pi(k + 1)], apex: 0 })
  for (let k = 0; k < 5; k++) sets.push({ idx: [1, qi(k), pi(k + 1), qi(k + 1)], apex: 1 })
  return pairLabels(solid(tens ? 'd10t' : 'd10', v, sets, 'vertex', 1), range(10, 0).map((x) => (tens ? (x === '0' ? '00' : x + '0') : x)))
}
const MAKERS: Record<Kind, () => Solid> = {
  d4: makeTetra,
  d6: () => {
    const v = signs((x, y, z) => [x, y, z])
    return pairLabels(solid('d6', v, fromNormals(v, [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]]), 'edge', 1.1), range(6))
  },
  d8: () => {
    const v: V3[] = [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]]
    return pairLabels(solid('d8', v, fromNormals(v, signs((x, y, z) => [x, y, z])), 'vertex', 1.05), range(8))
  },
  d10: () => makeTrap(false),
  d10t: () => makeTrap(true),
  d12: () => {
    const iv = icosaVerts(), v = icosaFaces(iv).map((t) => mean(t.map((i) => iv[i])))
    return pairLabels(solid('d12', v, fromNormals(v, iv), 'vertex', 1), range(12))
  },
  d20: () => {
    const v = icosaVerts()
    return pairLabels(solid('d20', v, icosaFaces(v).map((idx) => ({ idx })), 'vertex', 1), range(20))
  },
}
const SOLIDS: Partial<Record<Kind, Solid>> = {}
const solidOf = (k: Kind): Solid => (SOLIDS[k] ??= MAKERS[k]())

/** The die for a count of sides, or null for a number the game has no die for. */
function kindOfSides(sides: number): Kind | null {
  return ({ 4: 'd4', 6: 'd6', 8: 'd8', 10: 'd10', 12: 'd12', 20: 'd20' } as Record<number, Kind>)[sides] ?? null
}

/** The shapes and labels that show a rolled value. A d100 is a tens d10 and a units d10. A d10 shows 10 as 0. */
export function diceFor(sides: number, value: number): { kind: Kind; label: string }[] {
  if (sides === 100) {
    const tens = Math.floor((value % 100) / 10) * 10
    return [{ kind: 'd10t', label: tens === 0 ? '00' : String(tens) }, { kind: 'd10', label: String(value % 10) }]
  }
  const kind = kindOfSides(sides)
  return kind ? [{ kind, label: kind === 'd10' ? String(value % 10) : String(value) }] : []
}

const TARGETS = new Map<string, Mat>()
const RESTS = new Map<string, Pose>()
/** The turn that puts the face (a d4: the corner) with this label toward the camera, its number upright. */
function toLabel(kind: Kind, label: string): Mat {
  const key = `${kind}|${label}`
  let m = TARGETS.get(key)
  if (!m) TARGETS.set(key, (m = faceTurn(solidOf(kind), label)))
  return m
}
function faceTurn(s: Solid, label: string): Mat {
  let n: V3, v: V3
  if (s.d4) {
    const i = Number(label) - 1
    n = norm(s.verts[i])
    const w = s.verts[(i + 1) % 4]
    v = norm(sub(w, mul(n, dot(w, n))))
  } else {
    const f = s.faces.find((g) => g.label === label) ?? s.faces[0]
    n = f.n; v = f.up
  }
  return [...cross(v, n), ...v, ...n]
}
// A small tilt so a resting die still shows some depth. It is too small to turn a neighbour face toward the camera.
const TILT = compose(rotation([1, 0, 0], 0.16), rotation([0, 1, 0], 0.12))

export type Tone = 'plain' | 'gold' | 'red' | 'steel' | 'fire' | 'cold' | 'lightning' | 'acid' | 'poison' | 'necrotic' | 'radiant' | 'psychic' | 'force' | 'thunder'
interface Palette { ramp: string[]; ink: string; halo?: string }
export const TONES: Record<Tone, Palette> = {
  plain: { ramp: ['#26213a', '#3a3350', '#4b4366', '#5e5580'], ink: '#ece6d6' },
  gold: { ramp: ['#8a7143', '#a88c57', '#c9a96e', '#e2c88f'], ink: '#14121c', halo: '#e2c88f' },
  red: { ramp: ['#6e2626', '#8a3030', '#a33a3a', '#c55353'], ink: '#ece6d6' },
  steel: { ramp: ['#33383f', '#4c525d', '#6a7382', '#8e98a8'], ink: '#f2f4f8' },
  fire: { ramp: ['#5e2410', '#8f3a14', '#c4561b', '#ee8844'], ink: '#fff0dc' },
  cold: { ramp: ['#1d3552', '#2c5580', '#4580b0', '#78b4dc'], ink: '#f0f8ff' },
  lightning: { ramp: ['#2a2468', '#41379b', '#5b4fd0', '#8a80f0'], ink: '#f4f2ff' },
  acid: { ramp: ['#26521c', '#3b7a2a', '#58a83c', '#8ad466'], ink: '#14121c', halo: '#d6f5be' },
  poison: { ramp: ['#14403c', '#1f6660', '#2f8f86', '#5cc0b4'], ink: '#eafff9' },
  necrotic: { ramp: ['#0e0e16', '#191924', '#26263a', '#3c3c58'], ink: '#a8f08a' },
  radiant: { ramp: ['#8a8470', '#b5ae92', '#dcd5b4', '#f6f1d8'], ink: '#3a3320', halo: '#fffbe8' },
  psychic: { ramp: ['#5a1f55', '#84307c', '#b04aa6', '#d884cf'], ink: '#fde8fa' },
  force: { ramp: ['#5e2036', '#8a2f50', '#b8466f', '#e07a9c'], ink: '#fff0f5' },
  thunder: { ramp: ['#2a3f45', '#3d5c66', '#567f8c', '#7fa9b8'], ink: '#f0fbff' },
}
/** The die colour for a damage type. Slashing, piercing and bludgeoning share steel; an unknown type is plain. */
export function damageTone(type: string): Tone {
  const t = type.toLowerCase().trim()
  if (['slashing', 'piercing', 'bludgeoning'].includes(t)) return 'steel'
  return t in TONES && !['plain', 'gold', 'red', 'steel'].includes(t) ? (t as Tone) : 'plain'
}
const OUTLINE = '#14121c'
const LIGHT = norm([-0.35, 0.55, 0.75])
const rgb = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16))
function shade(tone: Tone, t: number): string {
  const r = TONES[tone].ramp
  const x = t * 3, i = Math.min(2, Math.floor(x)), f = x - i
  const a = rgb(r[i]), b = rgb(r[i + 1])
  return `rgb(${a.map((p, k) => Math.round(p + (b[k] - p) * f)).join(',')})`
}

export const FONT = '"Press Start 2P", "Pixel Digits", monospace'

type Pose = { M: Mat; hop: number; rest?: boolean }
interface Spin { a1: V3; a2: V3; w1: number; w2: number }
/** A random tumble. Pass a seeded `rand` (0 to 1) so that two screens tumble the same way. */
export function randomSpin(rand: () => number = Math.random): Spin {
  const r = () => rand() - 0.5
  return { a1: norm([r(), r(), r() + 0.01]), a2: norm([r(), 1, r()]), w1: (5 + rand() * 2) * Math.PI, w2: (3 + rand() * 2) * Math.PI }
}
export function restingPose(kind: Kind, label: string): Pose {
  const key = `${kind}|${label}`
  let p = RESTS.get(key)
  if (!p) RESTS.set(key, (p = { M: compose(TILT, toLabel(kind, label)), hop: 0, rest: true }))
  return p
}
/** Spin about two fixed axes. `k` is the turn left, 1 to 0: at 0 the die lies exactly on `label`. */
export function poseAt(kind: Kind, label: string, k: number, spin: Spin, hop = 0): Pose {
  if (k <= 0) return { ...restingPose(kind, label), hop }
  const M = compose(TILT, compose(rotation(spin.a1, spin.w1 * k), compose(rotation(spin.a2, spin.w2 * k), toLabel(kind, label))))
  return { M, hop }
}
/** The same, by time: `t` 0 to 1, slowing down to a stop. */
export const tumble = (kind: Kind, label: string, t: number, spin: Spin): Pose =>
  poseAt(kind, label, Math.pow(1 - t, 3), spin, Math.abs(Math.sin(t * Math.PI * 3)) * (1 - t) * (1 - t) * 0.04)

/** The numbers on a face: one in the middle, or on a d4 one at each corner. */
function faceTexts(s: Solid, f: Face): { p: V3; up: V3; em: number; s: string }[] {
  if (s.d4) return f.idx.map((i, k) => ({ p: add(f.c, mul(sub(s.verts[i], f.c), 0.56)), up: norm(sub(s.verts[i], f.c)), em: f.inr * 0.62, s: f.vlabels![k] }))
  const one = f.label.length === 1, ten = s.key === 'd10' || s.key === 'd10t'
  const k = f.idx.length === 3 ? (one ? 1.1 : 0.85) : f.idx.length === 4 && ten ? (one ? 1.15 : 0.9) : one ? 1.1 : 0.8
  const p = ten ? add(f.c, mul(f.up, f.inr * 0.25)) : f.idx.length === 3 ? add(f.c, mul(f.up, -f.inr * 0.1)) : f.c
  return [{ p, up: f.up, em: f.inr * k, s: f.label }]
}

/**
 * Draw the die. `size`: canvas pixels. `big`: the final number, drawn over the die and past its edge; it grows with
 * `big.t` (0 to 1, with a small overshoot). Without it, the faces carry their own numbers. `ts`: scale of those numbers.
 */
export function drawDie(ctx: CanvasRenderingContext2D, size: number, kind: Kind, pose: Pose, tone: Tone, big: { text: string; t: number } | null, ts = 1) {
  const s = solidOf(kind), pal = TONES[tone]
  ctx.setTransform(1, 0, 0, 1, 0, 0)
  ctx.clearRect(0, 0, size, size)
  const S = size * 0.4 * s.fit, cx = size / 2, cy = size * 0.5 - pose.hop * size
  const shadow = 1 - pose.hop * 4
  ctx.fillStyle = 'rgba(0,0,0,.35)'
  ctx.beginPath(); ctx.ellipse(cx, size * 0.9, size * 0.3 * shadow, size * 0.045 * shadow, 0, 0, 7); ctx.fill()
  const P = s.verts.map((v) => apply(pose.M, v))
  ctx.lineJoin = 'round'; ctx.lineCap = 'round'
  // A die at rest shows only the face that looks at us; a tumbling die shows every face it turns to the camera.
  const tmin = s.d4 ? 0.2 : pose.rest ? 0.9 : 0.4
  for (const f of s.faces) {
    const n = apply(pose.M, f.n)
    if (n[2] <= 0) continue
    ctx.beginPath()
    f.idx.forEach((i, k) => (k ? ctx.lineTo(cx + S * P[i][0], cy - S * P[i][1]) : ctx.moveTo(cx + S * P[i][0], cy - S * P[i][1])))
    ctx.closePath()
    ctx.fillStyle = shade(tone, Math.max(0, Math.min(1, dot(n, LIGHT) / 0.85)))
    ctx.fill()
    ctx.strokeStyle = OUTLINE; ctx.lineWidth = Math.max(1.2, size / 40); ctx.stroke()
    if (big || n[2] < tmin) continue
    for (const t of faceTexts(s, f)) {
      // The number lies in the face plane: its axes are the face's "right" and "up", turned by the pose.
      const q = apply(pose.M, t.p), up = apply(pose.M, t.up), right = apply(pose.M, cross(t.up, f.n))
      const k = ((S * t.em) / 20) * ts
      ctx.save()
      ctx.transform(k * right[0], -k * right[1], -k * up[0], k * up[1], cx + S * q[0], cy - S * q[1])
      ctx.font = `20px ${FONT}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
      ctx.fillStyle = pal.ink; ctx.fillText(t.s, 0, 0)
      ctx.restore()
    }
  }
  if (big) {
    const x = big.t, grow = 1 + 2.70158 * (x - 1) ** 3 + 1.70158 * (x - 1) ** 2
    // One size for every die; three digits shrink to fit.
    const em = size * 0.3 * grow * (big.text.length > 2 ? 2 / big.text.length : 1)
    ctx.font = `${em}px ${FONT}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
    ctx.lineJoin = 'round'; ctx.lineWidth = Math.max(2, em * 0.2)
    ctx.strokeStyle = pal.halo ?? OUTLINE; ctx.strokeText(big.text, cx, cy)
    ctx.fillStyle = pal.ink; ctx.fillText(big.text, cx, cy)
  }
}

/** Which label points at the camera under `pose` (a d4: which corner). Used by tests. */
export function facing(kind: Kind, pose: Pose): string {
  const s = solidOf(kind)
  let best = '', bz = -9
  if (s.d4) s.verts.forEach((v, i) => { const z = apply(pose.M, norm(v))[2]; if (z > bz) { bz = z; best = String(i + 1) } })
  else for (const f of s.faces) { const z = apply(pose.M, f.n)[2]; if (z > bz) { bz = z; best = f.label } }
  return best
}
/** Every label of a die. Used by tests. */
export const labelsOf = (kind: Kind): string[] => (solidOf(kind).d4 ? ['1', '2', '3', '4'] : solidOf(kind).faces.map((f) => f.label))
