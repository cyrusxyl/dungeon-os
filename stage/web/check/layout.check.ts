// Checks for lib/layout.ts. Run: node stage/web/check/layout.check.ts (Node 22.18+ strips the types).
// The cells come from the server (stage/cast.py, tested by tests/test_cast.py); this turns them into what the canvas draws.
import { layout } from '../src/lib/layout.ts'
import type { Room, Stand } from '../src/lib/scene.ts'

let failed = 0
const check = (label: string, ok: boolean, detail = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}${ok || !detail ? '' : `  (${detail})`}`)
  if (!ok) failed++
}

const grid = Array.from({ length: 8 }, (_, y) => Array.from({ length: 10 }, (_, x) => (x === 0 || y === 0 ? '#' : '.')).join(''))
const room: Room = { w: 10, h: 8, grid, props: [{ kind: 'barrel', x: 2, y: 2 }, { kind: 'table', x: 5, y: 4 }, { kind: 'rug', x: 5, y: 6, flat: true }] }
const key = (c: [number, number]) => `${c[0]},${c[1]}`

const placed = layout({ a: { side: 'party', cell: [3, 5], facing: 'right' }, b: { side: 'hostile', cell: [7, 2], facing: 'left' } }, [], room)
check('an actor stands on the cell the server gave, facing as it says', key(placed.find((p) => p.id === 'a')!.cell) === '3,5' && placed.find((p) => p.id === 'b')!.facing === 'left')
check('drawn back to front', placed.every((p, i) => i === 0 || placed[i - 1].cell[0] + placed[i - 1].cell[1] <= p.cell[0] + p.cell[1]))
check('a missing side is neutral', layout({ x: { cell: [3, 3] } }, [], room)[0].side === 'neutral')

// No cell yet (the gap before the server answers): a free floor cell, not a wall, not a prop that blocks, not a held cell.
const gap = layout({ a: { cell: [1, 1] }, b: {}, c: {} }, [], room)
check('an actor with no cell takes a free floor cell', gap.length === 3 && new Set(gap.map((p) => key(p.cell))).size === 3 && gap.every((p) => grid[p.cell[1]][p.cell[0]] === '.' && !['2,2', '5,4'].includes(key(p.cell))), gap.map((p) => key(p.cell)).join(' '))

// A throne with one seat, a bench with two. The point of a seat is in pixels of the prop's own picture.
const stand: Stand[] = [
  { slot: 'back_center', prop: 'throne', mode: 'sit', points: [[16, 84]], x: 5, y: 2 },
  { slot: 'mid_center', prop: 'bench_long', mode: 'sit', points: [[18, 14], [46, 14]], x: 5, y: 4 },
]
const on = layout({ arbiter: { side: 'neutral', on: 'back_center' }, a: { on: 'mid_center' }, b: { on: 'mid_center' }, c: { on: 'mid_center', cell: [4, 6] }, d: { on: 'nowhere', cell: [6, 6] } }, stand, room)
const get = (id: string) => on.find((p) => p.id === id)!
check('an actor on a prop stands on its cell, seated, at its point', key(get('arbiter').cell) === '5,2' && get('arbiter').sit && get('arbiter').spot?.point.join() === '16,84')
check('the next actor on the same prop takes the next point', get('a').spot?.point[0] === 18 && get('b').spot?.point[0] === 46)
check('an actor with no point left stands on its own cell', !get('c').onProp && !get('c').sit && !get('c').spot && key(get('c').cell) === '4,6')
check('an unknown slot is the floor too', !get('d').onProp && key(get('d').cell) === '6,6')

console.log(failed ? `\n${failed} failed` : '\nall passed')
process.exit(failed ? 1 : 0)
