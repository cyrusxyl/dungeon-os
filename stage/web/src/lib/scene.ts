// A scene as a small isometric room: what GET /api/scene/<location> returns (stage/scenes.py `room`), and the maths that
// hangs wall decor and seats an actor on a prop. Pure, so a check can run it (check/scene.check.ts).
import { HW, HH, type Geometry, type Pt } from './iso.ts'
import { BOX, plan, type PropEntry } from './props.ts'

export interface RoomProp {
  kind: string
  slot: string
  x: number
  y: number
  /** A flat prop (a rug, a trap) lies on the floor: an actor may stand on it. */
  flat?: boolean
}

export interface Decor {
  kind: string
  slot: string
  /** The wall it hangs on: north (n) or west (w). */
  wall: 'n' | 'w'
  /** Where along the wall its centre is, in cells. */
  t: number
  /** The row of a north wall, or the column of a west wall (0 in the fixed room). */
  line: number
  /** How high above the floor its lower edge hangs, in px. */
  lift: number
}

/** A prop an actor can sit on or stand on. `points` are in pixels of the prop's own (uncropped) picture. */
export interface Stand {
  slot: string
  prop: string
  mode: 'sit' | 'on'
  points: [number, number][]
  x: number
  y: number
}

/** Desk clutter: an icon in the sheet, set on a prop at a point of the prop's picture. */
export interface Stuff {
  /** The item icon it was cut from, such as `misc/misc_lamp.png`. */
  icon: string
  r: [number, number, number, number]
  on: string
  at: [number, number]
}

/** Where the pictures of a room lie in its sheet (`/asset/scene/<location>/room.png`): the floor first (a tile a cell). */
export interface Sheet {
  w: number
  h: number
  /** Rows of the wall faces and the caps of the north and the west wall; a tile a cell along the row. */
  north: [number, number]
  west: [number, number]
  stuff: number
}

export interface Room {
  w: number
  h: number
  /** `#` wall, `.` floor, as in the arena (the arena adds `d`, `~`, `-` and ` `). */
  grid: string[]
  props: { kind: string; x: number; y: number; flat?: boolean }[]
}

export interface SceneRoom extends Room {
  has_look: boolean
  mood: string
  /** True with no walls (a street, a forest). */
  open: boolean
  /** A room of a chosen shape: every wall cell takes its picture from the north strip. */
  shaped: boolean
  props: RoomProp[]
  decor: Decor[]
  stand: Stand[]
  stuff: Stuff[]
  sheet: Sheet
  /** How the blocks of the room look (stage/blocks.py, the `blocks` table of arena.json); null in a place with no blocks. */
  blocks_look?: { skin: 'flat' | 'wall' | 'floor'; colors: string[]; density: number } | null
}

/** A room with nothing in it, for actors that stand on no scene. */
export const blankRoom = (w = 14, h = 11): Room => ({ w, h, grid: Array.from({ length: h }, () => '.'.repeat(w)), props: [] })

/** The foot of a wall at the place `t` along it, in logical px: where the floor meets it. A north wall is the row `line`, a west wall the column. */
export function wallFoot(g: Geometry, wall: 'n' | 'w', t: number, line: number): Pt {
  return wall === 'n' ? [g.ox + HW * (t - line - 1), g.oy + HH * (t + line + 1)] : [g.ox + HW * (line + 1 - t), g.oy + HH * (line + 1 + t)]
}

/**
 * Where to anchor the sprite of a wall piece (a window, a fireplace). A north wall faces south-west and a west wall south-east,
 * so the piece is an ordinary prop of that face: its bands (a mantle, a thick frame) stand out from the wall. The anchor is the
 * foot moved forward by the depth of its back, and lifted. 4 px: the feet of a sprite lie a little below its anchor.
 */
export function decorAnchor(g: Geometry, d: Pick<Decor, 'wall' | 't' | 'lift' | 'line'>, back: number): Pt {
  const [x, y] = wallFoot(g, d.wall, d.t, d.line)
  return [x + (d.wall === 'n' ? -back : back), y + back / 2 - d.lift - 4]
}

/** The centre of a piece of decor `h` px high on the screen (logical px): where its light would be. */
export function decorCentre(g: Geometry, d: Pick<Decor, 'wall' | 't' | 'lift' | 'line'>, h = 32): Pt {
  const [x, y] = wallFoot(g, d.wall, d.t, d.line)
  return [x, y - d.lift - h / 2]
}

/**
 * Where a point of a prop's picture lies on the screen, from the ground centre of the prop's cell: (dx, dy) in logical px.
 * The point is in pixels of the uncropped picture, as `stand.points`. It follows the pose, so a point on a table top
 * lies on the top surface, and a seat point lies at the height of the seat. `face` sw is the picture as it is; se is turned over.
 */
export function pointOn(entry: PropEntry, face: 'sw' | 'se', px: number, py: number, box = BOX): Pt {
  const [w, h] = [entry.r[2], entry.r[3]]
  const x = px - entry.o[0]
  const y = py - entry.o[1]
  let X: number
  let Y: number
  if (entry.pose.pose === 'upright') {
    const k = Math.min(1, (box.cw - 16) / w, (box.ch - 24) / h)
    X = box.cx - (w * k) / 2 + x * k
    Y = box.cy + 4 - h * k + y * k
  } else {
    const { ops } = plan(w, h, entry.pose)
    const op = ops.find((o) => y >= o.seg.rs && y < o.seg.re) ?? ops[ops.length - 1]
    const m = op.m
    X = m[0] * x + m[2] * y + m[4]
    Y = m[1] * x + m[3] * y + m[5]
  }
  const dx = X - box.cx
  return [face === 'se' ? -dx : dx, Y - box.cy]
}
