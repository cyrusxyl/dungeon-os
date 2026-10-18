// Checks for lib/iso.ts. Run: node stage/web/check/iso.check.ts (Node 22.18+ strips the types).
import { byDepth, cellTop, CUT_H, facing, frameAt, geometry, groundCentre, hides, isCut, isFloor, pick, unitDepth, wallDepth, wallHeight, WALL_H } from '../src/lib/iso.ts'

let failed = 0
const check = (label: string, ok: boolean, detail = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}${ok || !detail ? '' : `  (${detail})`}`)
  if (!ok) failed++
}

// The canvas of a 10 x 8 room: ox = 8 * 32 + 8, oy = 48 + 70, width = 18 * 32 + 16, height = oy + 18 * 16 + 36.
const g = geometry(10, 8)
check('the canvas size and origin follow the plan', g.ox === 264 && g.oy === 118 && g.width === 592 && g.height === 442, JSON.stringify(g))
check('the top corner of cell (3, 2)', cellTop(g, 3, 2).join() === '296,198')
check('the ground centre of cell (3, 2) is 16 px lower', groundCentre(g, 3, 2).join() === '296,214')

// Picking: a point well inside the diamond (not on a corner, where a float error could pick the neighbour) gives the cell back.
const lost: string[] = []
for (let y = 0; y < g.h; y++) {
  for (let x = 0; x < g.w; x++) {
    const [cx, cy] = groundCentre(g, x, y)
    for (const [dx, dy] of [[0, 0], [28, 0], [-28, 0], [0, 12], [0, -12]]) {
      const [px, py] = pick(g, cx + dx, cy + dy)
      if (px !== x || py !== y) lost.push(`${x},${y}+${dx},${dy}->${px},${py}`)
    }
  }
}
check('picking a point inside each diamond gives that cell (centre and four near-corner points)', lost.length === 0, lost.slice(0, 4).join(' '))
check('a point left of the room is a cell outside it', pick(g, 2, g.oy + 40)[0] < 0 || pick(g, 2, g.oy + 40)[1] < 0)

// The cut rule on an L room. Floor: rows 1-2 from x 1 to 5, and rows 3-4 at x 1-2.
const L = ['#######', '#.....#', '#.....#', '#..####', '#..####', '#######']
const cut: string[] = []
for (let y = 0; y < L.length; y++) for (let x = 0; x < L[0].length; x++) if (L[y][x] === '#' && isCut(L, x, y)) cut.push(`${x},${y}`)
const want = ['6,1', '6,2', '3,3', '4,3', '5,3', '6,3', '3,4', '1,5', '2,5', '3,5']
check('the cut walls of an L room are the ones with floor behind them', cut.sort().join(' ') === want.sort().join(' '), cut.join(' '))
check('a cut wall is low and the others are full', wallHeight(L, 3, 3) === CUT_H && wallHeight(L, 0, 0) === WALL_H)
check('floor, a door gap and a hazard are floor; fog, void and wall are not', ['.', 'd', '~'].every(isFloor) && [' ', '-', '#', undefined].every((c) => !isFloor(c)))

check('a wall beside a cell never seen is cut: a low wall hides no unit', isCut([' #', '--'], 1, 0) && !isCut(['-#', '--'], 1, 0))

// A face is hidden by a wall as tall as itself, not by a low rim. In the L room, (6, 0) is tall and (6, 1) below it is cut.
check('a tall wall shows its face toward a low rim', !hides(L, 6, 1, 48))
check('a wall as tall as itself hides the face; open floor does not', hides(L, 6, 2, CUT_H) && !hides(L, 3, 1, 48))
check('a full wall hides the face of a low one', hides(L, 0, 2, CUT_H))

// Depth: a back wall first; a cut wall in front of the unit behind it and behind the unit before it.
check('an uncut wall draws before any unit', wallDepth(9, 9, false) < unitDepth(0, 0))
check('a cut wall draws after a unit on the cell beside it and before a unit in front', unitDepth(2, 3) < wallDepth(3, 3, true) && wallDepth(3, 3, true) < unitDepth(3, 3))
const order = byDepth([{ depth: 2, n: 'b' }, { depth: 1, n: 'a' }, { depth: 2, n: 'c' }, { depth: 0, n: 'z' }]).map((t) => t.n).join('')
check('the depth sort is back to front and stable', order === 'zabc', order)

// A 64 frame has its feet at row 60; a bigger frame has them 4 rows above its bottom too.
check('a 64 frame stands with its feet on the ground centre', frameAt(g, 3, 2).join() === '264,154', frameAt(g, 3, 2).join())
check('a 96 frame is centred and lower-aligned the same way', frameAt(g, 3, 2, 96, 96).join() === '248,122', frameAt(g, 3, 2, 96, 96).join())

// Facing: all eight moves. The screen turns the grid by 45 degrees.
const faces = ([[0, -1], [1, -1], [1, 0], [1, 1], [0, 1], [-1, 1], [-1, 0], [-1, -1]] as const).map(([dx, dy]) => facing(dx, dy)).join()
check('all eight moves', faces === 'up,right,right,down,left,left,up,up', faces)
check('a zero move faces down', facing(0, 0) === 'down')

if (failed) process.exit(1)
console.log('all passed')
