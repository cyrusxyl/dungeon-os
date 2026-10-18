// Checks for lib/layout.ts. Run: node stage/web/check/layout.check.ts (Node 22.18+ strips the types).
import { readFileSync } from 'node:fs'
import { layout, MAX_ACTORS, type ActorState } from '../src/lib/layout.ts'
import type { Room, Stand } from '../src/lib/scene.ts'

let failed = 0
const check = (label: string, ok: boolean, detail = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}${ok || !detail ? '' : `  (${detail})`}`)
  if (!ok) failed++
}

// The room of a tavern: walls on the north row and the west column, a barrel and a table in it.
const grid = Array.from({ length: 8 }, (_, y) => Array.from({ length: 10 }, (_, x) => (x === 0 || y === 0 ? '#' : '.')).join(''))
const room: Room = { w: 10, h: 8, grid, props: [{ kind: 'barrel', x: 2, y: 2 }, { kind: 'table', x: 5, y: 4 }, { kind: 'rug', x: 5, y: 6, flat: true }] }
const across = (c: [number, number]) => c[0] - c[1]
const key = (c: [number, number]) => `${c[0]},${c[1]}`

// 12 actors: 4 party, 2 allies, 2 neutral, 4 hostile. The old fold put all but five at `center`.
const twelve: Record<string, ActorState> = {}
for (const [i, side] of (['party', 'party', 'party', 'party', 'ally', 'ally', 'neutral', 'neutral', 'hostile', 'hostile', 'hostile', 'hostile'] as const).entries()) {
  twelve[`a${i}`] = { side, position: 'center' }
}
const cast = layout(twelve, [], room)
check('every actor is placed', cast.length === MAX_ACTORS)
check('no two actors stand on the same cell', new Set(cast.map((p) => key(p.cell))).size === cast.length, cast.map((p) => key(p.cell)).join(' '))
check('all stand on floor, not on a wall or a prop that blocks', cast.every((p) => grid[p.cell[1]][p.cell[0]] === '.' && !['2,2', '5,4'].includes(key(p.cell))), cast.map((p) => key(p.cell)).join(' '))
check('the party stands left of the hostile on the screen', Math.max(...cast.filter((p) => p.side === 'party' || p.side === 'ally').map((p) => across(p.cell))) < Math.min(...cast.filter((p) => p.side === 'hostile').map((p) => across(p.cell))),
  cast.map((p) => `${p.side}:${across(p.cell)}`).join(' '))
check('drawn back to front', cast.every((p, i) => i === 0 || cast[i - 1].cell[0] + cast[i - 1].cell[1] <= p.cell[0] + p.cell[1]))
check('the party faces right and the hostile left', cast.filter((p) => p.side === 'party').every((p) => p.facing === 'right') && cast.filter((p) => p.side === 'hostile').every((p) => p.facing === 'left'))

// The same twelve in a room with no walls and no props: they still fit and stay apart.
const open: Room = { w: 10, h: 8, grid: Array.from({ length: 8 }, () => '.'.repeat(10)), props: [] }
const wide = layout(twelve, [], open)
check('twelve fit in an open room, each on its own cell', wide.length === 12 && new Set(wide.map((p) => key(p.cell))).size === 12)

const alone = layout({ gareth: { side: 'neutral' } }, [], room)
check('one neutral NPC stands at the back, in the middle of the screen', Math.abs(across(alone[0].cell)) <= 1 && alone[0].cell[0] + alone[0].cell[1] <= 9, key(alone[0].cell))
const talk = layout({ sireth: { side: 'party' }, gareth: { side: 'neutral' } }, [], room)
const at = (id: string) => talk.find((p) => p.id === id)!
check('a neutral stands beside the party when no one opposes it, and faces it', across(at('gareth').cell) > across(at('sireth').cell) && at('gareth').facing === 'left')
check('a missing side is neutral', layout({ x: {} }, [], room)[0].side === 'neutral')

// A throne with one seat, a bench with two. The point of a seat is in pixels of the prop's own picture.
const stand: Stand[] = [
  { slot: 'back_center', prop: 'throne', mode: 'sit', points: [[16, 84]], x: 5, y: 2 },
  { slot: 'mid_center', prop: 'bench_long', mode: 'sit', points: [[18, 14], [46, 14]], x: 5, y: 4 },
]
const on = layout({ arbiter: { side: 'neutral', on: 'back_center' }, a: { on: 'mid_center' }, b: { on: 'mid_center' }, c: { on: 'mid_center' }, d: { on: 'nowhere' } }, stand, room)
const get = (id: string) => on.find((p) => p.id === id)!
check('an actor on a prop stands on its cell, seated, at its point', key(get('arbiter').cell) === '5,2' && get('arbiter').sit && get('arbiter').spot?.point.join() === '16,84')
check('the next actor on the same prop takes the next point', get('a').spot?.point[0] === 18 && get('b').spot?.point[0] === 46)
check('an actor with no point left stands on the floor', !get('c').onProp && !get('c').sit && !get('c').spot)
check('an unknown slot is the floor too', !get('d').onProp)
const crowd = layout({ arbiter: { side: 'neutral', on: 'back_center' }, a: { side: 'neutral' }, b: { side: 'neutral' }, c: { side: 'neutral' } }, stand, room)
const front = new Set(['5,2', '6,2', '5,3', '6,3'])
check('no floor actor stands in front of someone on a prop', crowd.filter((p) => !p.onProp).every((p) => !front.has(key(p.cell))), crowd.map((p) => key(p.cell)).join(' '))
check('a scene with no stand points does not place anyone on a prop', layout({ x: { on: 'back_center' } }, [], room)[0].onProp === false)

// The same cases in layout_cases.json are checked by tests/test_cast.py against stage/cast.py: the two layouts must agree.
const cases = JSON.parse(readFileSync(new URL('./layout_cases.json', import.meta.url), 'utf8'))
for (const c of cases) {
  const got = layout(c.actors, c.stand, c.room).map(({ id, side, cell, facing, sit, onProp }) => ({ id, side, cell, facing, sit, onProp }))
  check(`fixture: ${c.name}`, JSON.stringify(got) === JSON.stringify(c.cast))
}

console.log(failed ? `\n${failed} failed` : '\nall passed')
process.exit(failed ? 1 : 0)
