// Checks for lib/props.ts. Run: node stage/web/check/props.check.ts (Node 22.18+ strips the types).
import { clampSplits, dominantColor, plan, segments, shade, tintPixels, type Pose } from '../src/lib/props.ts'

let failed = 0
const check = (label: string, ok: boolean, detail = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}${ok || !detail ? '' : `  (${detail})`}`)
  if (!ok) failed++
}
const same = (a: ArrayLike<number>, b: number[]) => a.length === b.length && b.every((v, i) => Math.abs(a[i] - v) < 1e-9)

// Splits keep at least 2 rows a band. The tuned water_trough has [2, 2, 16] on 4 bands.
check('close splits move apart', clampSplits([2, 2, 16], 4, 31).join() === '2,4,16', clampSplits([2, 2, 16], 4, 31).join())
check('a split too low or too high is clamped', clampSplits([0], 2, 20).join() === '2' && clampSplits([99], 2, 20).join() === '18')
check('one band has no split', clampSplits([5], 1, 20).length === 0)

// A cabinet-like pose on a 20 x 10 picture: a top band lying flat (3 rows, depth x5), then a front band standing (7 rows, thickness 15).
const cabinet: Extract<Pose, { pose: 'bands' }> = { pose: 'bands', first: 'H', splits: [3], bands: [[5, 0], [1, 15]], width: 0.8 }
const segs = segments(cabinet, 10)
check('the bands alternate from the first', segs.map((s) => s.t).join() === 'H,V' && segs.map((s) => `${s.rs}-${s.re}`).join() === '0-3,3-10')
// By hand: W = 16, Hpx = 15, Vpx = 7, vt = 15, span = 46, k = 1 (it fits the box).
// Ox = 128 - 8 + 7.5 - 7.5 = 120. Oy = 200 - 4 - 3.75 + 3.75 + 4 = 200. The chain starts at z = 7, vp = 0.
// H band: e = 120, f = 200 - 7 = 193, c = -5, d = 2.5; centre of the side clip = 120 + 8 - 7.5 = 120.5.
// V band after it: vp = 15, e = 120 - 15 = 105, f = 200 + 7.5 - 7 - 3 = 197.5.
const p = plan(20, 10, cabinet)
check('the fit scale is 1', p.k === 1)
check('the horizontal band matrix', p.ops[0].t === 'H' && same(p.ops[0].m, [0.8, 0.4, -5, 2.5, 120, 193]), p.ops[0].m.join())
check('the clip of its side face', p.ops[0].t === 'H' && p.ops[0].cxS === 120.5)
check('the vertical band matrix', p.ops[1].t === 'V' && same(p.ops[1].m, [0.8, 0.4, 0, 1, 105, 197.5]), p.ops[1].m.join())
check('no vertical band is first, so none gets a top strip', p.ops[1].t === 'V' && !p.ops[1].first)

// A bookshelf-like prop starting with a vertical band: it is first and gets the top strip. Two vertical bands share the height.
const shelf: Extract<Pose, { pose: 'bands' }> = { pose: 'bands', first: 'V', splits: [4], bands: [[1, 6], [2, 0]] }
const q = plan(10, 10, shelf)
// The bands alternate, so the second band is flat: Hpx = 6 * 2 = 12, Vpx = 4.
check('the first band is vertical with a top strip', q.ops[0].t === 'V' && q.ops[0].first)
check('the second band lies flat', q.ops[1].t === 'H')
// W = 10, span = 10 + 12 + 6 = 28, k = 1; Ox = 128 - 5 + 6 - 3 = 126; Oy = 200 - 2.5 - 3 + 1.5 + 4 = 200. z starts at 4.
check('the top band hangs from the full height', q.ops[0].t === 'V' && same(q.ops[0].m, [1, 0.5, 0, 1, 126, 196]), q.ops[0].m.join())

// A big picture shrinks to fit the box: k < 1.
const big = plan(400, 10, cabinet)
check('a picture wider than the box is scaled down', big.k < 1 && big.k > 0, String(big.k))

// The made faces use the most common colour.
const px = (r: number, g: number, b: number, a = 255) => [r, g, b, a]
const data = [...px(200, 40, 40), ...px(200, 41, 41), ...px(10, 220, 10), ...px(5, 5, 5), ...px(250, 250, 250, 100)]
check('the dominant colour skips clear and dark pixels', dominantColor(data).join() === '204,44,44', dominantColor(data).join())
check('a clear picture gets a default brown', dominantColor(px(0, 0, 0, 0)).join() === '120,90,70')
check('shade scales and clamps', shade([100, 200, 255], 1.22).join() === '122,244,255' && shade([100, 200, 255], 0.62).join() === '62,124,158')

// tint: a 2 x 4 picture. Column 0 is opaque in rows 1-3, column 1 in rows 0 and 2.
const A = 255
const pic = [
  0, 0, 0, 0, 9, 9, 9, A,
  9, 9, 9, A, 0, 0, 0, 0,
  9, 9, 9, A, 9, 9, 9, A,
  9, 9, 9, A, 0, 0, 0, 0,
]
const alpha = (arr: Uint8ClampedArray) => Array.from({ length: 8 }, (_, i) => (arr[i * 4 + 3] ? 1 : 0)).join('')
check('silhouette keeps every opaque pixel', alpha(tintPixels(pic, 2, 4, [1, 2, 3], 'sil')) === '01' + '10' + '11' + '10')
check('top keeps the first two opaque rows of a column', alpha(tintPixels(pic, 2, 4, [1, 2, 3], 'top')) === '01' + '10' + '10' + '00', alpha(tintPixels(pic, 2, 4, [1, 2, 3], 'top')))
check('a tint reaches only the rows asked for', alpha(tintPixels(pic, 2, 4, [1, 2, 3], 'sil', 2, 4)) === '00' + '00' + '11' + '10')

if (failed) process.exit(1)
console.log('all passed')
