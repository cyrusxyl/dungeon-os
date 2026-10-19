// Checks for lib/scene.ts. Run: node stage/web/check/scene.check.ts (Node 22.18+ strips the types).
import { geometry } from '../src/lib/iso.ts'
import { backDepth, faceOf, type PropEntry } from '../src/lib/props.ts'
import { blankRoom, decorAnchor, decorCentre, pointOn, wallFoot } from '../src/lib/scene.ts'

let failed = 0
const check = (label: string, ok: boolean, detail = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}${ok || !detail ? '' : `  (${detail})`}`)
  if (!ok) failed++
}
const same = (a: ArrayLike<number>, b: number[]) => a.length === b.length && b.every((v, i) => Math.abs(a[i] - v) < 1e-9)

// Wall decor on a 10 x 8 room: ox = 264, oy = 118. The foot of the north wall at t = 2.5 is where floor meets wall: x = 264 + 32 (2.5 - 1),
// y = 118 + 16 (2.5 + 1). A west wall at t = 2.5: x = 264 + 32 (1 - 2.5), y = 118 + 16 (1 + 2.5).
const g = geometry(10, 8)
check('the foot of the north wall', same(wallFoot(g, 'n', 2.5, 0), [264 + 32 * 1.5, 118 + 16 * 3.5]), wallFoot(g, 'n', 2.5, 0).join())
check('the foot of the west wall', same(wallFoot(g, 'w', 2.5, 0), [264 + 32 * -1.5, 118 + 16 * 3.5]), wallFoot(g, 'w', 2.5, 0).join())
check('a wall on another line moves both ways: north row 3, west column 4', same(wallFoot(g, 'n', 2.5, 3), [264 + 32 * (2.5 - 4), 118 + 16 * (2.5 + 4)]) && same(wallFoot(g, 'w', 2.5, 4), [264 + 32 * (5 - 2.5), 118 + 16 * (5 + 2.5)]))
check('a piece stands out from the wall by the depth of its back, and hangs at its lift',
  same(decorAnchor(g, { wall: 'n', t: 2.5, lift: 14, line: 0 }, 6), [264 + 48 - 6, 118 + 56 + 3 - 14 - 4]) && same(decorAnchor(g, { wall: 'w', t: 2.5, lift: 0, line: 0 }, 6), [264 - 48 + 6, 118 + 56 + 3 - 4]))
check('the centre of a piece is above its foot by its lift and half its height', same(decorCentre(g, { wall: 'n', t: 2.5, lift: 10, line: 0 }, 40), [264 + 48, 118 + 56 - 10 - 20]))
check('a room with nothing in it is open floor', blankRoom().grid.every((r) => r === '.'.repeat(14)) && blankRoom().props.length === 0)

// A point of a prop's picture on the screen. Upright: a 32 x 32 picture stands with its feet on the ground centre (+4).
const upright: PropEntry = { r: [0, 0, 32, 32], o: [0, 0], size: [32, 32], pose: { pose: 'upright' } }
check('the middle of an upright picture is above the ground centre', same(pointOn(upright, 'sw', 16, 16), [0, -12]), pointOn(upright, 'sw', 16, 16).join())
check('a point right of the middle is right of the centre, and the other face turns it over', pointOn(upright, 'sw', 24, 16)[0] === 8 && pointOn(upright, 'se', 24, 16)[0] === -8)
const cropped: PropEntry = { r: [0, 0, 20, 30], o: [6, 2], size: [32, 32], pose: { pose: 'upright' } }
// The point (16, 17) is (10, 15) in the cropped 20 x 30 picture: its middle across, and 15 rows from the top.
check('the crop offset is taken off the point', same(pointOn(cropped, 'sw', 16, 17), [0, -11]), pointOn(cropped, 'sw', 16, 17).join())
// A cabinet-like prop (20 x 10, a flat top of 3 rows, then a front of 7 rows, width 0.8): its matrices are in check/props.check.ts.
// The top band is flat: a point 1.5 rows down the top lies at e + a * x + c * y: 120 + 0.8 * 10 + -5 * 1.5 = 120.5 -> dx = 120.5 - 128.
const cabinet: PropEntry = { r: [0, 0, 20, 10], o: [0, 0], size: [20, 10], pose: { pose: 'bands', first: 'H', splits: [3], bands: [[5, 0], [1, 15]], width: 0.8 } }
const top = pointOn(cabinet, 'sw', 10, 1.5)
check('a point on the flat top follows the top band', same(top, [120 + 0.8 * 10 - 5 * 1.5 - 128, 0.4 * 10 + 2.5 * 1.5 + 193 - 200]), top.join())
const front = pointOn(cabinet, 'sw', 10, 6)
check('a point on the front follows the front band', same(front, [105 + 0.8 * 10 - 128, 0.4 * 10 + 1 * 6 + 197.5 - 200]), front.join())

// A prop turns toward the middle of the room: right of the centre it faces south-west (to the left), left of it south-east.
check('a prop faces the middle of the room', faceOf(8, 2, [5, 4]) === 'sw' && faceOf(2, 6, [5, 4]) === 'se' && faceOf(5, 4, [5, 4]) === 'sw')
// The back of a prop is the thickness of its first vertical band. The cabinet starts flat, so its back is 0; a fireplace-like pose is not.
const hearth: PropEntry = { r: [0, 0, 32, 40], o: [0, 0], size: [32, 40], pose: { pose: 'bands', first: 'V', splits: [20], bands: [[1, 6], [1, 4]] } }
check('the back depth follows the first vertical band', backDepth(hearth) === 6 && backDepth(cabinet) === 0 && backDepth(upright) === 0)

if (failed) process.exit(1)
console.log('all passed')
