// Where each actor stands on the 320 x 192 stage. Pure, so a check can run it (check/layout.check.ts).
// The DM never gives a pixel: an actor's side picks its place (party left, hostile right, the others at the back
// or beside the party), and `@enter <id> on <slot>` puts it on a prop's stand point (see stage/scenes.py stand_points).
import type { Position, Side } from '@/lib/stage'

export const STAGE_W = 320
export const MAX_ACTORS = 12
/** Feet line of each depth row. A frame is drawn so its feet row (60) lands here. */
export const ROW_FEET = { back: 122, mid: 142, front: 162 } as const
type Row = keyof typeof ROW_FEET

export interface StandSpot {
  slot: string
  prop: string
  mode: 'sit' | 'on'
  points: [number, number][]
}
export interface ActorState {
  position?: Position
  side?: Side
  on?: string
  emotion?: string
}
export interface Placed {
  id: string
  side: Side
  /** Centre column and the row the feet (or, seated, the hip) stand on. */
  x: number
  y: number
  facing: 'down' | 'left' | 'right'
  sit: boolean
  /** True when the actor is on a prop: no depth row, and no ring when seated. */
  onProp: boolean
}

const RANK: Record<string, number> = { 'far-left': 0, left: 1, center: 2, right: 3, 'far-right': 4 }
const LEFT: [number, number] = [0, 146]
const RIGHT: [number, number] = [168, 296]
const MIDDLE: [number, number] = [70, 250]
const KEEP_CLEAR = 26 // px between a floor actor and someone on a prop

/** Fill `ids` into rows over [x0, x1]: the rows alternate, and a later row is staggered so heads show between bodies. */
function fill(ids: string[], [x0, x1]: [number, number], rows: Row[], out: Map<string, { x: number; y: number }>) {
  const cols = Math.max(1, Math.ceil(ids.length / rows.length))
  const step = (x1 - x0) / cols
  ids.forEach((id, i) => {
    const r = i % rows.length
    const x = x0 + step * (Math.floor(i / rows.length) + 0.5) + (r ? Math.min(step / 2, 24) : 0)
    out.set(id, { x: Math.round(Math.max(32, Math.min(STAGE_W - 32, x))), y: ROW_FEET[rows[r]] })
  })
}

export function layout(actors: Record<string, ActorState>, stand: StandSpot[] = []): Placed[] {
  const placed: Placed[] = []
  const used = new Map<string, number>()
  const rest: [string, ActorState][] = []
  for (const [id, a] of Object.entries(actors)) {
    const spot = a.on ? stand.find((s) => s.slot === a.on) : undefined
    const n = spot ? (used.get(spot.slot) ?? 0) : 0
    if (spot && n < spot.points.length) {
      used.set(spot.slot, n + 1)
      const [x, y] = spot.points[n]
      placed.push({ id, side: a.side ?? 'neutral', x, y, facing: 'down', sit: spot.mode === 'sit', onProp: true })
    } else {
      rest.push([id, a])
    }
  }
  const side = (a: ActorState): Side => a.side ?? 'neutral'
  const sorted = (f: (a: ActorState) => boolean) =>
    rest.filter(([, a]) => f(a)).sort(([, a], [, b]) => (RANK[a.position ?? 'center'] ?? 2) - (RANK[b.position ?? 'center'] ?? 2)).map(([id]) => id)
  const party = sorted((a) => side(a) === 'party' || side(a) === 'ally')
  const hostile = sorted((a) => side(a) === 'hostile')
  const neutral = sorted((a) => side(a) === 'neutral')
  const rows = (n: number): Row[] => (n > 8 ? ['front', 'mid', 'back'] : ['front', 'mid'])

  const at = new Map<string, { x: number; y: number }>()
  fill(party, LEFT, rows(party.length), at)
  fill(hostile, RIGHT, rows(hostile.length), at)
  // Neutrals stand beside the party when no one opposes it, else at the back between the two sides.
  const beside = hostile.length === 0 && party.length > 0
  fill(neutral, beside ? RIGHT : MIDDLE, beside ? rows(neutral.length) : ['back'], at)

  // Keep clear of anyone on a prop: a body in front of a seat or a table top would hide who sits or stands there.
  const taken = placed.map((p) => p.x)
  for (const [id] of rest) {
    const p = at.get(id)!
    const near = taken.find((x) => Math.abs(p.x - x) < KEEP_CLEAR)
    if (near !== undefined) {
      const x = p.x < near ? near - KEEP_CLEAR : near + KEEP_CLEAR
      at.set(id, { ...p, x: Math.max(32, Math.min(STAGE_W - 32, x)) })
    }
  }

  for (const [id, a] of rest) {
    const s = side(a)
    const p = at.get(id)!
    const facing = s === 'party' || s === 'ally' ? 'right' : s === 'hostile' || beside ? 'left' : 'down'
    placed.push({ id, side: s, x: p.x, y: p.y, facing, sit: false, onProp: false })
  }
  // Back to front, so a nearer actor covers a farther one.
  return placed.sort((a, b) => a.y - b.y)
}
