// Where each actor stands in a scene room, in cells. Pure, so a check can run it (check/layout.check.ts).
// The DM never gives a cell: an actor's side picks its place (party on the left of the screen, hostile on the right, the
// others at the back or beside the party), and `@enter <id> on <slot>` puts it on a prop's stand point (see stage/scenes.py).
// On the screen a cell (x, y) lies at s = x - y across and d = x + y deep: the layout works in those two.
import type { Room, Stand } from './scene.ts'
import type { Position, Side } from './stage.ts'

export const MAX_ACTORS = 12

export interface ActorState {
  position?: Position
  side?: Side
  on?: string
  emotion?: string
}
export interface Placed {
  id: string
  side: Side
  cell: [number, number]
  facing: 'down' | 'left' | 'right'
  sit: boolean
  /** True when the actor is on a prop: no depth row, and no ring when seated. */
  onProp: boolean
  /** The prop and the point of its picture the actor is on. */
  spot?: { stand: Stand; point: [number, number] }
}

const RANK: Record<string, number> = { 'far-left': 0, left: 1, center: 2, right: 3, 'far-right': 4 }
/** The depth of each row of actors, as a fraction of the way from the back of the floor to the front. */
const ROW_DEPTH = { back: 0.27, mid: 0.48, front: 0.69 } as const
type Row = keyof typeof ROW_DEPTH

/** Spread `n` actors over the rows: the rows alternate, and a later row is staggered so heads show between bodies. */
function targets(n: number, [s0, s1]: [number, number], rows: Row[], depth: (f: number) => number): [number, number][] {
  const cols = Math.max(1, Math.ceil(n / rows.length))
  const step = (s1 - s0) / cols
  return Array.from({ length: n }, (_, i) => {
    const r = i % rows.length
    return [s0 + step * (Math.floor(i / rows.length) + 0.5) + (r ? Math.min(step / 2, 0.75) : 0), depth(ROW_DEPTH[rows[r]])]
  })
}

export function layout(actors: Record<string, ActorState>, stand: Stand[] = [], room: Room): Placed[] {
  const placed: Placed[] = []
  const used = new Map<string, number>()
  const rest: [string, ActorState][] = []
  const taken = new Set(room.props.filter((p) => !p.flat).map((p) => `${p.x},${p.y}`))
  for (const [id, a] of Object.entries(actors)) {
    const spot = a.on ? stand.find((s) => s.slot === a.on) : undefined
    const n = spot ? (used.get(spot.slot) ?? 0) : 0
    if (spot && n < spot.points.length) {
      used.set(spot.slot, n + 1)
      placed.push({ id, side: a.side ?? 'neutral', cell: [spot.x, spot.y], facing: 'down', sit: spot.mode === 'sit', onProp: true, spot: { stand: spot, point: spot.points[n] } })
      // Keep clear of anyone on a prop: a body in front of a seat or a table top would hide who sits or stands there.
      for (const c of [[1, 0], [0, 1], [1, 1]]) taken.add(`${spot.x + c[0]},${spot.y + c[1]}`)
    } else {
      rest.push([id, a])
    }
  }
  const floor: [number, number][] = []
  room.grid.forEach((row, y) => [...row].forEach((c, x) => c === '.' && !taken.has(`${x},${y}`) && floor.push([x, y])))
  const ss = floor.map(([x, y]) => x - y)
  const ds = floor.map(([x, y]) => x + y)
  const [sLo, sHi, dLo, dHi] = [Math.min(...ss), Math.max(...ss), Math.min(...ds), Math.max(...ds)]
  const mid = (sLo + sHi) / 2
  const half = (sHi - sLo) / 2
  const across = (a: number, b: number): [number, number] => [mid + half * a, mid + half * b]
  const depth = (f: number) => dLo + f * (dHi - dLo)

  const side = (a: ActorState): Side => a.side ?? 'neutral'
  const sorted = (f: (a: ActorState) => boolean) =>
    rest.filter(([, a]) => f(a)).sort(([, a], [, b]) => (RANK[a.position ?? 'center'] ?? 2) - (RANK[b.position ?? 'center'] ?? 2)).map(([id]) => id)
  const party = sorted((a) => side(a) === 'party' || side(a) === 'ally')
  const hostile = sorted((a) => side(a) === 'hostile')
  const neutral = sorted((a) => side(a) === 'neutral')
  const rows = (n: number): Row[] => (n > 8 ? ['front', 'mid', 'back'] : ['front', 'mid'])
  // Neutrals stand beside the party when no one opposes it, else at the back between the two sides.
  const beside = hostile.length === 0 && party.length > 0

  const wanted = new Map<string, [number, number]>()
  const want = (ids: string[], list: [number, number][]) => ids.forEach((id, i) => wanted.set(id, list[i]))
  want(party, targets(party.length, across(-0.92, -0.08), rows(party.length), depth))
  want(hostile, targets(hostile.length, across(0.08, 0.92), rows(hostile.length), depth))
  want(neutral, beside ? targets(neutral.length, across(0.08, 0.92), rows(neutral.length), depth) : targets(neutral.length, across(-0.45, 0.45), ['back'], depth))

  // Each actor takes the free cell nearest its wanted place; the back rows choose first.
  const free = new Set(floor.map(([x, y]) => `${x},${y}`))
  const order = [...wanted.entries()].sort(([, a], [, b]) => a[1] - b[1] || a[0] - b[0])
  const at = new Map<string, [number, number]>()
  for (const [id, [s, d]] of order) {
    let best: [number, number] | null = null
    let cost = Infinity
    for (const [x, y] of floor) {
      if (!free.has(`${x},${y}`)) continue
      const c = (x - y - s) ** 2 + 0.8 * (x + y - d) ** 2
      if (c < cost) {
        cost = c
        best = [x, y]
      }
    }
    if (!best) continue
    free.delete(`${best[0]},${best[1]}`)
    at.set(id, best)
  }
  for (const [id, a] of rest) {
    const cell = at.get(id)
    if (!cell) continue
    const s = side(a)
    const facing = s === 'party' || s === 'ally' ? 'right' : s === 'hostile' || beside ? 'left' : 'down'
    placed.push({ id, side: s, cell, facing, sit: false, onProp: false })
  }
  // Back to front, so a nearer actor covers a farther one.
  return placed.sort((a, b) => a.cell[0] + a.cell[1] - (b.cell[0] + b.cell[1]))
}
