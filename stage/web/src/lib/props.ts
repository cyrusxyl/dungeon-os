// A prop in the isometric view: one picture cut into 1 to 4 bands, each standing up (V) or lying flat (H)
// (see isometric-view.md, "Prop poses"; port of iso-prototype/bands.js). The maths is pure, so a check can run it
// (check/props.check.ts). The canvas code is thin and touches the DOM only when called.

export const SIDE = 0.62 // made side face of a vertical band
export const TOPL = 1.22 // made top strip of the first band
export const SLAB = 0.6 // made side face of a horizontal band
const SLAB_LEFT = 0.78 // the left half of a horizontal band's side face

export type Rgb = [number, number, number]
export type Matrix = [number, number, number, number, number, number]
export type Pose =
  | { pose: 'upright' }
  | { pose: 'bands'; first: 'V' | 'H'; splits: number[]; bands: [number, number][]; width?: number }

/** One prop of GET /api/props: its rect in the atlas, the crop offset and full size of its picture, its pose. */
export interface PropEntry {
  r: [number, number, number, number]
  o: [number, number]
  size: [number, number]
  pose: Pose
}

/** A prop that lies flat on the floor (a rug, a trap): one horizontal band with no thickness. */
export const isFlat = (pose: Pose): boolean => pose.pose === 'bands' && pose.bands.length === 1 && pose.first === 'H' && pose.bands[0][1] === 0

export interface Seg {
  /** Rows of the picture, from the top: rs up to re. */
  rs: number
  re: number
  t: 'V' | 'H'
  /** Size scales the height of a V band and the depth of an H band. Thickness is the made side face. */
  size: number
  thick: number
}

const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v))

/** The rows where the bands end. A band keeps at least 2 rows, so close splits (a tuned [2, 2, 16]) move apart. */
export function clampSplits(splits: number[], bands: number, h: number): number[] {
  let prev = 0
  return splits.slice(0, bands - 1).map((v, j) => (prev = clamp(v, prev + 2, h - 2 * (bands - 1 - j))))
}

/** The bands of a pose on a picture `h` rows high, from the top down. They alternate, starting with `first`. */
export function segments(pose: Extract<Pose, { pose: 'bands' }>, h: number): Seg[] {
  const cuts = clampSplits(pose.splits, pose.bands.length, h)
  return [0, ...cuts].map((rs, j) => ({
    rs,
    re: j < cuts.length ? cuts[j] : h,
    t: (j % 2 === 0) === (pose.first === 'V') ? 'V' : 'H',
    size: pose.bands[j][0],
    thick: pose.bands[j][1],
  }))
}

/** The sprite box (logical px) the finished prop must fit, and where its ground centre lies in it. */
export const BOX = { cw: 256, ch: 256, cx: 128, cy: 200 }

export type Op =
  | { t: 'V'; seg: Seg; m: Matrix; first: boolean }
  | { t: 'H'; seg: Seg; m: Matrix; cxS: number }

export interface Plan {
  /** Fit scale, at most 1. */
  k: number
  ops: Op[]
}

/** The matrices (logical px) that stand each band of a picture `w` x `h` on the ground centre (cx, cy). */
export function plan(w: number, h: number, pose: Extract<Pose, { pose: 'bands' }>, box = BOX): Plan {
  const { cw, ch, cx, cy } = box
  const ws = pose.width ?? 1
  const segs = segments(pose, h)
  const rows = (s: Seg) => (s.re - s.rs) * s.size
  const Vpx = segs.filter((s) => s.t === 'V').reduce((t, s) => t + rows(s), 0)
  const Hpx = segs.filter((s) => s.t === 'H').reduce((t, s) => t + rows(s), 0)
  const vt = Math.max(0, ...segs.filter((s) => s.t === 'V').map((s) => s.thick))
  const ht = Math.max(0, ...segs.filter((s) => s.t === 'H').map((s) => s.thick))
  const W = w * ws
  const span = W + Hpx + vt
  const k = Math.min(1, (cw - 20) / span, (ch - 30) / (Vpx + 0.5 * span + ht))
  const Ox = cx - (k * W) / 2 + (k * Hpx) / 2 - (k * vt) / 2
  const Oy = cy - 0.25 * k * W - 0.25 * k * Hpx + 0.25 * k * vt + 4
  let z = Vpx
  let vp = 0
  const ops: Op[] = segs.map((seg, j) => {
    const n = seg.re - seg.rs
    if (seg.t === 'V') {
      const e = Ox - k * vp
      const f = Oy + 0.5 * k * vp - k * z - k * seg.size * seg.rs
      z -= n * seg.size
      return { t: 'V', seg, m: [k * ws, 0.5 * k * ws, 0, k * seg.size, e, f], first: j === 0 }
    }
    const D = seg.size
    const e = Ox - k * vp + k * D * seg.rs
    const f = Oy + 0.5 * k * vp - 0.5 * k * D * seg.rs - k * z
    const cxS = Ox + (k * W) / 2 - k * (vp + (n * D) / 2)
    vp += n * D
    return { t: 'H', seg, m: [k * ws, 0.5 * k * ws, -k * D, 0.5 * k * D, e, f], cxS }
  })
  return { k, ops }
}

/** The most common colour of a picture (5 bits a channel), ignoring clear and dark pixels. The made faces use it. */
export function dominantColor(data: ArrayLike<number>): Rgb {
  const count = new Map<number, number>()
  for (let i = 0; i < data.length; i += 4) {
    if (data[i + 3] < 200 || 0.3 * data[i] + 0.59 * data[i + 1] + 0.11 * data[i + 2] < 45) continue
    const key = ((data[i] >> 3) << 10) | ((data[i + 1] >> 3) << 5) | (data[i + 2] >> 3)
    count.set(key, (count.get(key) ?? 0) + 1)
  }
  let best: number | null = null
  let most = 0
  for (const [key, n] of count) {
    if (n > most) {
      most = n
      best = key
    }
  }
  if (best === null) return [120, 90, 70]
  return [(((best >> 10) & 31) << 3) | 4, (((best >> 5) & 31) << 3) | 4, ((best & 31) << 3) | 4]
}

export const shade = (c: Rgb, f: number): Rgb => c.map((v) => clamp(Math.round(v * f), 0, 255)) as Rgb

/**
 * The outline of rows r0 to r1 of a picture in one colour. Mode `sil` keeps every opaque pixel; mode `top` keeps the
 * first two opaque rows of each column.
 */
export function tintPixels(data: ArrayLike<number>, w: number, h: number, rgb: Rgb, mode: 'sil' | 'top', r0 = 0, r1 = h): Uint8ClampedArray<ArrayBuffer> {
  const out = new Uint8ClampedArray(w * h * 4)
  for (let x = 0; x < w; x++) {
    let top = -1
    for (let y = r0; y < r1; y++) {
      if (data[(y * w + x) * 4 + 3] <= 128) continue
      if (top < 0) top = y
      if (mode === 'sil' || y <= top + 1) {
        const o = (y * w + x) * 4
        out[o] = rgb[0]
        out[o + 1] = rgb[1]
        out[o + 2] = rgb[2]
        out[o + 3] = 255
      }
    }
  }
  return out
}

// ---- canvas ----

/** A finished prop: draw `canvas` at (groundX * S + dx, groundY * S + dy), with the canvas drawn 1:1 on the 2x board. */
export interface Baked {
  canvas: HTMLCanvasElement
  dx: number
  dy: number
}

const SC = 2
type Make = () => HTMLCanvasElement
const newCanvas: Make = () => document.createElement('canvas')

function bandsToCanvas(src: HTMLCanvasElement, data: Uint8ClampedArray, w: number, h: number, pose: Extract<Pose, { pose: 'bands' }>, make: Make): HTMLCanvasElement {
  const { cw, ch } = BOX
  const out = make()
  out.width = cw * SC
  out.height = ch * SC
  const o = out.getContext('2d')!
  o.imageSmoothingEnabled = false
  const T = (m: Matrix, dy = 0) => o.setTransform(SC * m[0], SC * m[1], SC * m[2], SC * m[3], SC * m[4], SC * (m[5] + dy))
  const tint = (rgb: Rgb, mode: 'sil' | 'top', seg: Seg) => {
    const c = make()
    c.width = w
    c.height = h
    c.getContext('2d')!.putImageData(new ImageData(tintPixels(data, w, h, rgb, mode, seg.rs, seg.re), w, h), 0, 0)
    return c
  }
  const color = dominantColor(data)
  const { k, ops } = plan(w, h, pose)
  const made: (() => void)[] = []
  const art: (() => void)[] = []
  for (const op of ops) {
    const { seg } = op
    const n = seg.re - seg.rs
    const rows = (img: CanvasImageSource) => o.drawImage(img, 0, seg.rs, w, n, 0, seg.rs, w, n)
    if (op.t === 'V') {
      const sil = tint(shade(color, SIDE), 'sil', seg)
      const imgs = op.first ? [sil, tint(shade(color, TOPL), 'top', seg)] : [sil]
      made.push(() => {
        for (const img of imgs) {
          for (let t = seg.thick; t >= 1; t--) {
            T([op.m[0], op.m[1], 0, op.m[3], op.m[4] + t * k, op.m[5] - (t * k) / 2])
            rows(img)
          }
        }
      })
      art.push(() => {
        T(op.m)
        rows(src)
      })
    } else {
      const a = tint(shade(color, SLAB), 'sil', seg)
      const b = tint(shade(color, SLAB_LEFT), 'sil', seg)
      made.push(() => {
        for (let t = seg.thick * k; t > 0; t -= 0.5) {
          T(op.m, t)
          rows(a)
        }
        o.save()
        o.setTransform(1, 0, 0, 1, 0, 0)
        o.beginPath()
        o.rect(0, 0, SC * op.cxS, SC * ch)
        o.clip()
        for (let t = seg.thick * k; t > 0; t -= 0.5) {
          T(op.m, t)
          rows(b)
        }
        o.restore()
      })
      art.push(() => {
        T(op.m)
        rows(src)
      })
    }
  }
  made.forEach((f) => f())
  art.forEach((f) => f())
  return out
}

function uprightToCanvas(src: HTMLCanvasElement, w: number, h: number, make: Make): HTMLCanvasElement {
  const { cw, ch, cx, cy } = BOX
  const out = make()
  out.width = cw * SC
  out.height = ch * SC
  const o = out.getContext('2d')!
  o.imageSmoothingEnabled = false
  const k = Math.min(1, (cw - 16) / w, (ch - 24) / h)
  o.setTransform(SC * k, 0, 0, SC * k, SC * (cx - (w * k) / 2), SC * (cy + 4 - h * k))
  o.drawImage(src, 0, 0)
  return out
}

/** Cut the clear border off a sprite; `dx`, `dy` tell where its corner lies from the ground centre, in canvas px. */
function trim(full: HTMLCanvasElement, make: Make): Baked {
  const { cx, cy } = BOX
  const { width, height } = full
  const px = full.getContext('2d')!.getImageData(0, 0, width, height).data
  let x0 = width
  let y0 = height
  let x1 = -1
  let y1 = -1
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if (px[(y * width + x) * 4 + 3] === 0) continue
      x0 = Math.min(x0, x)
      x1 = Math.max(x1, x)
      y0 = Math.min(y0, y)
      y1 = Math.max(y1, y)
    }
  }
  const canvas = make()
  if (x1 < 0) {
    canvas.width = canvas.height = 1
    return { canvas, dx: 0, dy: 0 }
  }
  canvas.width = x1 - x0 + 1
  canvas.height = y1 - y0 + 1
  canvas.getContext('2d')!.drawImage(full, x0, y0, canvas.width, canvas.height, 0, 0, canvas.width, canvas.height)
  return { canvas, dx: x0 - SC * cx, dy: y0 - SC * cy }
}

/** Build one prop pose facing south-west. */
export function bakeProp(atlas: CanvasImageSource, entry: PropEntry, make: Make = newCanvas): Baked {
  const [rx, ry, w, h] = entry.r
  const src = make()
  src.width = w
  src.height = h
  const sc = src.getContext('2d', { willReadFrequently: true })!
  sc.drawImage(atlas, rx, ry, w, h, 0, 0, w, h)
  const data = sc.getImageData(0, 0, w, h).data
  const full = entry.pose.pose === 'upright' ? uprightToCanvas(src, w, h, make) : bandsToCanvas(src, data, w, h, entry.pose, make)
  return trim(full, make)
}

/** The same prop facing south-east: the finished sprite turned over, about the ground centre. */
export function mirror(b: Baked, make: Make = newCanvas): Baked {
  const canvas = make()
  canvas.width = b.canvas.width
  canvas.height = b.canvas.height
  const c = canvas.getContext('2d')!
  c.setTransform(-1, 0, 0, 1, canvas.width, 0)
  c.drawImage(b.canvas, 0, 0)
  return { canvas, dx: -(b.dx + b.canvas.width), dy: b.dy }
}

const cache = new Map<string, Baked>()

/** A prop sprite, built once per atlas, name and face. */
export function propSprite(atlas: CanvasImageSource, key: string, name: string, entry: PropEntry, face: 'sw' | 'se'): Baked {
  const id = `${key}|${name}|${face}`
  let b = cache.get(id)
  if (!b) {
    b = face === 'sw' ? bakeProp(atlas, entry) : mirror(propSprite(atlas, key, name, entry, 'sw'))
    cache.set(id, b)
  }
  return b
}

/** The face of a prop on cell (x, y): it turns toward the middle of the room, so a chair at the right looks left and the reverse. */
export function faceOf(x: number, y: number, centre: [number, number]): 'sw' | 'se' {
  return x - y >= centre[0] - centre[1] ? 'sw' : 'se'
}

/** How far the back of a prop lies behind its front picture, in logical px (the thickness of its first vertical band). */
export function backDepth(entry: PropEntry): number {
  if (entry.pose.pose === 'upright') return 0
  const { k, ops } = plan(entry.r[2], entry.r[3], entry.pose)
  return ops[0].t === 'V' ? ops[0].seg.thick * k : 0
}
