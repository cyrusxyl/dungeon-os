// The 2:1 isometric view of a room (see isometric-view.md, "Geometry"). The scene and the arena use it.
// The maths is pure, so a check can run it (check/iso.check.ts). The canvas functions are thin and touch the DOM only when called.

export const HW = 32 // half the width of a cell diamond
export const HH = 16 // half the height of a cell diamond
export const S = 2 // the canvas draws at twice the logical size
export const WALL_H = 48 // a full wall block
export const CUT_H = 12 // a wall block that stands in front of floor
export const FEET_ROW = 60 // the row of an actor frame (64 x 64) where the feet are

export type Pt = [number, number]

/** Floor cells: floor, door gap, hazard. A cell never seen (` `) and the void outside a room (`-`) are not. */
export const isFloor = (c: string | undefined): boolean => c === '.' || c === 'd' || c === '~'
export const isWall = (c: string | undefined): boolean => c === '#'
const at = (grid: string[], x: number, y: number): string | undefined => grid[y]?.[x]

export interface Geometry {
  w: number
  h: number
  /** Logical origin of the top corner of cell (0, 0). */
  ox: number
  oy: number
  /** Logical size of the canvas. */
  width: number
  height: number
}

export function geometry(w: number, h: number, wallH = WALL_H): Geometry {
  const oy = wallH + 70
  return { w, h, ox: h * HW + 8, oy, width: (w + h) * HW + 16, height: oy + (w + h) * HH + 36 }
}

/** The top corner of the diamond of cell (x, y). */
export const cellTop = (g: Geometry, x: number, y: number): Pt => [g.ox + (x - y) * HW, g.oy + (x + y) * HH]

/** Where feet stand on cell (x, y): the centre of the diamond. */
export const groundCentre = (g: Geometry, x: number, y: number): Pt => {
  const [px, py] = cellTop(g, x, y)
  return [px, py + HH]
}

/** The cell under a point of the canvas (logical pixels). The point may lie outside the room. */
export function pick(g: Geometry, mx: number, my: number): Pt {
  const rx = mx - g.ox
  const ry = my - g.oy
  return [Math.floor((rx / HW + ry / HH) / 2), Math.floor((ry / HH - rx / HW) / 2)]
}

/** The middle of the floor of a room, in cells: props turn to face it. */
export function roomCentre(grid: string[]): Pt {
  const cells = grid.flatMap((row, y) => [...row].flatMap((c, x) => (isFloor(c) ? [[x, y]] : [])))
  const xs = cells.map((c) => c[0])
  const ys = cells.map((c) => c[1])
  return cells.length ? [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2] : [0, 0]
}

/**
 * A wall cell is cut low when floor lies at (x-1, y), (x, y-1) or (x-1, y-1): it stands in front of that floor.
 * A cell never seen (` `) counts as floor here: a low wall never hides a unit, so this is the safe guess.
 */
export const isCut = (grid: string[], x: number, y: number): boolean => {
  const behind = (c: string | undefined) => isFloor(c) || c === ' '
  return behind(at(grid, x - 1, y)) || behind(at(grid, x, y - 1)) || behind(at(grid, x - 1, y - 1))
}

export const wallHeight = (grid: string[], x: number, y: number): number => (isCut(grid, x, y) ? CUT_H : WALL_H)

/** The sort key of a wall block: a cut wall stands just in front of its row; the others draw first. */
export const wallDepth = (x: number, y: number, cut: boolean): number => (cut ? x + y - 0.4 : -1 + (x + y) * 0.001)
/** The sort key of a unit or a prop on cell (x, y). */
export const unitDepth = (x: number, y: number): number => x + y + 0.01

/** Back to front. The sort is stable. */
export const byDepth = <T extends { depth: number }>(things: T[]): T[] => [...things].sort((a, b) => a.depth - b.depth)

export type Facing = 'up' | 'down' | 'left' | 'right'

/** The LPC facing for a move of (dx, dy) cells. The screen turns the grid by 45 degrees. */
export function facing(dx: number, dy: number): Facing {
  const sx = dx - dy
  const sy = dx + dy
  if (sy < 0) return 'up'
  if (sx < 0) return 'left'
  if (sx > 0) return 'right'
  return 'down'
}

/**
 * A piece of a picture: a tile of a sheet, 32 wide. A floor tile or an arena wall is 32 x 32. A wall face may be taller
 * (`sh` rows, a front-facing wall of a scene); `cap` is then the row where its 32 x 32 top cap starts.
 */
export interface Tex {
  img: CanvasImageSource
  sx: number
  sy: number
  sh?: number
  cap?: number
}

export interface Style {
  floor: (x: number, y: number, c: string) => Tex | undefined
  /** A second tile over the floor tile (a door gap, a hazard). */
  floorOver?: (x: number, y: number, c: string) => Tex | undefined
  wall: (x: number, y: number) => Tex | undefined
  /** A cell the party has seen but cannot see now (dim light): its floor and wall get a shade. */
  dim?: (x: number, y: number) => boolean
}

/** A wall block that stands in front of units: it draws in depth order, not into the base. */
export interface Rim {
  x: number
  y: number
  depth: number
  draw: (ctx: CanvasRenderingContext2D) => void
}

export interface Base {
  canvas: HTMLCanvasElement
  rims: Rim[]
}

const tileAt = (ctx: CanvasRenderingContext2D, t: Tex, dx: number, dy: number, dw: number, dh: number, sy = t.sy, sh = 32) =>
  ctx.drawImage(t.img, t.sx, sy, 32, sh, dx, dy, dw, dh)

const DIM = 'rgba(8,6,14,0.62)'

function drawFloorTile(ctx: CanvasRenderingContext2D, t: Tex, px: number, py: number, dim = false) {
  ctx.save()
  ctx.setTransform(S, S / 2, -S, S / 2, S * px, S * py)
  tileAt(ctx, t, 0, 0, 32.7, 32.7) // 0.7 extra hides the seams
  if (dim) {
    ctx.fillStyle = DIM
    ctx.fillRect(0, 0, 32.7, 32.7)
  }
  ctx.restore()
}

/** True when the cell beyond a face is a wall at least as tall as this one: it covers the face. A low rim does not. */
export const hides = (grid: string[], x: number, y: number, h: number): boolean => isWall(at(grid, x, y)) && h <= wallHeight(grid, x, y)

/** One block of wall: two sheared faces below a top cap. A face is drawn when the cell beyond it is not a wall. */
export function drawWallBlock(ctx: CanvasRenderingContext2D, grid: string[], x: number, y: number, px: number, py: number, h: number, t: Tex, dim = false) {
  const face = (shear: number, fx: number, fy: number, shade: number) => {
    ctx.save()
    ctx.setTransform(S, S * shear, 0, S, S * fx, S * (fy - h))
    if (t.sh) {
      tileAt(ctx, t, 0, 0, 32, h, t.sy, t.sh)
    } else if (h <= 32) {
      tileAt(ctx, t, 0, 0, 32, h, t.sy, h)
    } else {
      tileAt(ctx, t, 0, h - 32, 32, 32)
      tileAt(ctx, t, 0, 0, 32, h - 32, t.sy + 64 - h, h - 32)
    }
    ctx.fillStyle = `rgba(8,4,16,${shade})`
    ctx.fillRect(0, 0, 32, h)
    if (dim) {
      ctx.fillStyle = DIM
      ctx.fillRect(0, 0, 32, h)
    }
    ctx.restore()
  }
  if (!hides(grid, x, y + 1, h)) face(0.5, px - HW, py + HH, 0.22)
  if (!hides(grid, x + 1, y, h)) face(-0.5, px, py + 2 * HH, 0.42)
  ctx.save()
  ctx.setTransform(S, S / 2, -S, S / 2, S * px, S * (py - h))
  tileAt(ctx, t, 0, 0, 32.7, 32.7, t.cap ?? t.sy)
  ctx.fillStyle = 'rgba(255,240,220,0.16)'
  ctx.fillRect(0, 0, 32.7, 32.7)
  if (dim) {
    ctx.fillStyle = DIM
    ctx.fillRect(0, 0, 32.7, 32.7)
  }
  ctx.restore()
}

/**
 * The part of a room that does not move: the floor and the wall blocks that stand behind everything. Draw it once, and
 * again only when the room or the fog changes. The cut walls come back as `rims` to draw in depth order with the units.
 */
export function buildBase(g: Geometry, grid: string[], style: Style, make = () => document.createElement('canvas')): Base {
  const canvas = make()
  canvas.width = g.width * S
  canvas.height = g.height * S
  const ctx = canvas.getContext('2d')!
  ctx.imageSmoothingEnabled = false
  ctx.fillStyle = '#000'
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  const rims: Rim[] = []
  const walls: { x: number; y: number }[] = []
  for (let y = 0; y < g.h; y++) {
    for (let x = 0; x < g.w; x++) {
      const c = grid[y]?.[x]
      if (isFloor(c)) {
        const [px, py] = cellTop(g, x, y)
        const t = style.floor(x, y, c!)
        const dim = style.dim?.(x, y) ?? false
        if (t) drawFloorTile(ctx, t, px, py, dim)
        const over = style.floorOver?.(x, y, c!)
        if (over) drawFloorTile(ctx, over, px, py, dim)
      } else if (isWall(c)) {
        walls.push({ x, y })
      }
    }
  }
  for (const { x, y } of walls.sort((a, b) => a.x + a.y - (b.x + b.y))) {
    const t = style.wall(x, y)
    if (!t) continue
    const cut = isCut(grid, x, y)
    const h = cut ? CUT_H : WALL_H
    const [px, py] = cellTop(g, x, y)
    const dim = style.dim?.(x, y) ?? false
    if (cut) rims.push({ x, y, depth: wallDepth(x, y, true), draw: (c) => drawWallBlock(c, grid, x, y, px, py, h, t, dim) })
    else drawWallBlock(ctx, grid, x, y, px, py, h, t, dim)
  }
  return { canvas, rims }
}

/** A diamond over cell (x, y) in the floor layer: a range, an aim area, a hover or a turn marker. */
export function diamond(ctx: CanvasRenderingContext2D, g: Geometry, x: number, y: number, fill?: string, stroke?: string, lineWidth = 1) {
  const [px, py] = cellTop(g, x, y)
  ctx.setTransform(S, 0, 0, S, 0, 0)
  ctx.beginPath()
  ctx.moveTo(px, py)
  ctx.lineTo(px + HW, py + HH)
  ctx.lineTo(px, py + 2 * HH)
  ctx.lineTo(px - HW, py + HH)
  ctx.closePath()
  if (fill) {
    ctx.fillStyle = fill
    ctx.fill()
  }
  if (stroke) {
    ctx.strokeStyle = stroke
    ctx.lineWidth = lineWidth
    ctx.stroke()
  }
}

/**
 * Where to draw an actor frame so its feet stand on the ground centre of cell (x, y). The feet are 4 rows above the
 * bottom of the frame (row 60 of 64); a big monster has a bigger frame.
 */
export const frameAt = (g: Geometry, x: number, y: number, width = 64, height = 64): Pt => {
  const [cx, cy] = groundCentre(g, x, y)
  return [Math.round(cx - width / 2), Math.round(cy - (height - (64 - FEET_ROW)))]
}
