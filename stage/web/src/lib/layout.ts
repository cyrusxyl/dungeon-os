// Where each actor stands in a scene room, in cells. Pure, so a check can run it (check/layout.check.ts).
// The server chooses the cells (stage/cast.py) and keeps them on the actors. This turns them into what the canvas draws:
// an actor on a prop stands at a point of its picture, and one with no cell yet (the gap before the server answers) takes a free cell.
import type { Room, Stand } from './scene.ts'
import type { Side } from './stage.ts'

export interface ActorState {
  side?: Side
  on?: string
  emotion?: string
  cell?: [number, number]
  facing?: 'down' | 'left' | 'right' | 'up'
}
export interface Placed {
  id: string
  side: Side
  cell: [number, number]
  facing: 'down' | 'left' | 'right' | 'up'
  sit: boolean
  /** True when the actor is on a prop: no depth row, and no ring when seated. */
  onProp: boolean
  /** The prop and the point of its picture the actor is on. */
  spot?: { stand: Stand; point: [number, number] }
}

export function layout(actors: Record<string, ActorState>, stand: Stand[] = [], room: Room): Placed[] {
  const placed: Placed[] = []
  const used = new Map<string, number>()
  const held = new Set<string>()
  const waiting: [string, ActorState][] = []
  for (const [id, a] of Object.entries(actors)) {
    const spot = a.on ? stand.find((s) => s.slot === a.on) : undefined
    const n = spot ? (used.get(spot.slot) ?? 0) : 0
    if (spot && n < spot.points.length) {
      used.set(spot.slot, n + 1)
      placed.push({ id, side: a.side ?? 'neutral', cell: [spot.x, spot.y], facing: 'down', sit: spot.mode === 'sit', onProp: true, spot: { stand: spot, point: spot.points[n] } })
    } else if (a.cell) {
      held.add(`${a.cell[0]},${a.cell[1]}`)
      placed.push({ id, side: a.side ?? 'neutral', cell: a.cell, facing: a.facing ?? 'down', sit: false, onProp: false })
    } else {
      waiting.push([id, a])
    }
  }
  // Back to front, so a nearer actor covers a farther one.
  const back = () => placed.sort((a, b) => a.cell[0] + a.cell[1] - (b.cell[0] + b.cell[1]))
  if (!waiting.length) return back()
  const solid = new Set(room.props.filter((p) => !p.flat).map((p) => `${p.x},${p.y}`))
  const floor: [number, number][] = []
  room.grid.forEach((row, y) => [...row].forEach((c, x) => c === '.' && !solid.has(`${x},${y}`) && !held.has(`${x},${y}`) && floor.push([x, y])))
  for (const [id, a] of waiting) {
    const cell = floor.shift()
    if (cell) placed.push({ id, side: a.side ?? 'neutral', cell, facing: a.facing ?? 'down', sit: false, onProp: false })
  }
  return back()
}
