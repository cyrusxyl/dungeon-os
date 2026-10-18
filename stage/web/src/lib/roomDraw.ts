// Drawing that the scene and the combat board share: a prop of a room, in depth order with the units.
import { buildBase, groundCentre, S, unitDepth, WALL_H, type Base, type Geometry, type Pt, type Style, type Tex } from '@/lib/iso'
import type { PropsInfo } from '@/lib/propAtlas'
import { backDepth, faceOf, isFlat, propSprite } from '@/lib/props'
import { decorAnchor, type SceneRoom } from '@/lib/scene'
import { T } from '@/lib/tiles'

/** Something to draw in depth order: a low wall, a prop, a unit. */
export interface Thing {
  depth: number
  draw: () => void
}

/** The depth of a flat prop: before every wall and unit. */
export const FLAT_DEPTH = -0.5

/** A prop standing on cell (x, y) of a room, or nothing when the catalogue has no pose for it. `dim`: the party cannot see it now. */
export function propThing(ctx: CanvasRenderingContext2D, g: Geometry, props: PropsInfo, atlas: HTMLImageElement, p: { kind: string; x: number; y: number }, centre: Pt, dim = false): Thing | undefined {
  const entry = props.props[p.kind]
  if (!entry) return undefined
  return {
    depth: isFlat(entry.pose) ? FLAT_DEPTH : unitDepth(p.x, p.y),
    draw: () => {
      const sprite = propSprite(atlas, props.atlas, p.kind, entry, faceOf(p.x, p.y, centre))
      const [cx, cy] = groundCentre(g, p.x, p.y)
      ctx.setTransform(1, 0, 0, 1, 0, 0)
      if (dim) ctx.filter = 'brightness(0.45)'
      ctx.drawImage(sprite.canvas, Math.round(cx * S + sprite.dx), Math.round(cy * S + sprite.dy))
      if (dim) ctx.filter = 'none'
    },
  }
}

/** A shaped room cuts its wall pictures from the north strip, which is as wide as the fixed room. */
const SHAPED_STRIP = 10
/** The west strip has 8 pictures; the low rim of the fixed room (south row, east column) reuses them. */
const WEST_STRIP = 8

/** The floor and wall tiles of a scene room, cut from its sheet. `extra` adds to the style (the board adds hazards and fog). */
export function sceneStyle(room: SceneRoom, sheet: HTMLImageElement | undefined, extra: Partial<Style> = {}): Style {
  const { north, west } = room.sheet
  const wall = (x: number, y: number): Tex | undefined => {
    if (!sheet) return undefined
    const [col, [face, cap]] = room.shaped || y === 0 ? [x % SHAPED_STRIP, north] : [y % WEST_STRIP, west]
    return { img: sheet, sx: col * T, sy: face, sh: WALL_H, cap }
  }
  return { floor: (x, y) => sheet && { img: sheet, sx: x * T, sy: y * T }, wall, ...extra }
}

/** The floor, the walls and the wall decor of a scene room: they do not move, so they are drawn once. */
export function sceneBase(room: SceneRoom, grid: string[], g: Geometry, style: Style, props: PropsInfo | undefined, atlas: HTMLImageElement | undefined): Base {
  const base = buildBase(g, grid, style)
  const ctx = base.canvas.getContext('2d')!
  if (props && atlas) {
    for (const d of room.decor) {
      const entry = props.props[d.kind]
      if (!entry) continue
      const sprite = propSprite(atlas, props.atlas, d.kind, entry, d.wall === 'n' ? 'sw' : 'se')
      const [x, y] = decorAnchor(g, d, backDepth(entry))
      ctx.setTransform(1, 0, 0, 1, 0, 0)
      if (d.wall === 'w') ctx.filter = 'brightness(0.8)' // the west wall faces away from the light
      ctx.drawImage(sprite.canvas, Math.round(x * S + sprite.dx), Math.round(y * S + sprite.dy))
      ctx.filter = 'none'
    }
  }
  return base
}
