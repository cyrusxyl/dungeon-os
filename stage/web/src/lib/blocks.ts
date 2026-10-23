// Blocks: low walls, ledges and stubs in a room (see blocks.md, stage/blocks.py). A block cell is a prop of kind `block_*`.
// The scene and the combat board both draw it with `blockThing`, in depth order with the figures.
// A block in front of a figure fades, so the figure shows through (`fadedBlocks`).
import { HH, HW, isWall, S, cellTop, unitDepth, wallHeight, type Geometry } from '@/lib/iso'
import type { Thing } from '@/lib/roomDraw'
import type { SceneRoom } from '@/lib/scene'
import { BLOCK_PX, type BlockMap } from '@/lib/blockMap'
import { T } from '@/lib/tiles'

/** The north strip of the room sheet has 14 wall pictures; the first and the last are edges, so a block uses the 12 between. */
const STRIP = 12
/** How clear a block is when a figure stands behind it. */
const FADE = 0.3
const SHADE = { left: 0.78, right: 0.6, top: 1.15 }

function shade(hex: string, f: number): string {
  const n = parseInt(hex.slice(1), 16)
  const c = (v: number) => Math.min(255, Math.round(v * f))
  return `rgb(${c((n >> 16) & 255)},${c((n >> 8) & 255)},${c(n & 255)})`
}

/**
 * A block cell as a thing to draw in depth order. `sheet` is the picture of the room (floor tiles, and the wall strips the sides and
 * the top may be cut from). With no sheet yet, or a flat look, the block is plain color.
 */
export function blockThing(
  ctx: CanvasRenderingContext2D,
  g: Geometry,
  room: Pick<SceneRoom, 'grid' | 'sheet' | 'blocks_look'>,
  sheet: HTMLImageElement | undefined,
  p: { kind: string; x: number; y: number },
  map: BlockMap,
  faded: Set<string>,
  dim = false,
): Thing {
  const h = BLOCK_PX[p.kind]
  const look = room.blocks_look ?? { skin: 'flat' as const, colors: ['#7b8190'], density: 30 }
  const textured = look.skin !== 'flat' && sheet !== undefined
  const key = `${p.x},${p.y}`
  const colour = look.colors[(map.tint.get(key) ?? 0) % look.colors.length]
  const heightAt = (x: number, y: number): number => {
    const c = room.grid[y]?.[x]
    return c && isWall(c) ? wallHeight(room.grid, x, y) : (map.height.get(`${x},${y}`) ?? 0)
  }
  return {
    depth: unitDepth(p.x, p.y),
    draw: () => {
      const [px, py] = cellTop(g, p.x, p.y)
      ctx.save()
      if (faded.has(key)) ctx.globalAlpha = FADE
      const col = 1 + ((p.x * 3 + p.y * 5) % STRIP)
      const [faceY, capY] = room.sheet.north
      const face = (side: 'L' | 'R', z0: number) => {
        const fx = side === 'L' ? px - HW : px
        const fy = side === 'L' ? py + HH : py + 2 * HH
        const sh = side === 'L' ? 0.5 : -0.5
        ctx.save()
        if (!textured) {
          ctx.setTransform(S, 0, 0, S, 0, 0)
          ctx.beginPath()
          ctx.moveTo(fx, fy - z0)
          ctx.lineTo(fx + HW, fy - z0 + sh * HW)
          ctx.lineTo(fx + HW, fy - h + sh * HW)
          ctx.lineTo(fx, fy - h)
          ctx.closePath()
          ctx.fillStyle = shade(colour, side === 'L' ? SHADE.left : SHADE.right)
          ctx.fill()
          ctx.strokeStyle = 'rgba(0,0,0,0.28)'
          ctx.lineWidth = 1
          ctx.stroke()
        } else {
          ctx.setTransform(S, S * sh, 0, S, S * fx, S * fy)
          ctx.beginPath()
          ctx.rect(0, -h, 32, h - z0)
          ctx.clip()
          for (let k = Math.floor(z0 / 48); k < Math.ceil(h / 48); k++) ctx.drawImage(sheet!, col * T, faceY, 32, 48, 0, -48 * (k + 1), 32, 48)
          ctx.fillStyle = `rgba(8,4,16,${side === 'L' ? 0.22 : 0.42})`
          ctx.fillRect(0, -h, 32, h - z0)
        }
        ctx.restore()
      }
      const lower = (x: number, y: number) => Math.min(h, heightAt(x, y))
      if (h > heightAt(p.x, p.y + 1)) face('L', lower(p.x, p.y + 1))
      if (h > heightAt(p.x + 1, p.y)) face('R', lower(p.x + 1, p.y))
      // The top.
      if (!textured) {
        ctx.setTransform(S, 0, 0, S, 0, 0)
        ctx.beginPath()
        ctx.moveTo(px, py - h)
        ctx.lineTo(px + HW, py + HH - h)
        ctx.lineTo(px, py + 2 * HH - h)
        ctx.lineTo(px - HW, py + HH - h)
        ctx.closePath()
        ctx.fillStyle = shade(colour, SHADE.top)
        ctx.fill()
        ctx.strokeStyle = 'rgba(0,0,0,0.22)'
        ctx.lineWidth = 1
        ctx.stroke()
      } else {
        ctx.setTransform(S, S / 2, -S, S / 2, S * px, S * (py - h))
        if (look.skin === 'floor') ctx.drawImage(sheet!, p.x * T, p.y * T, 32, 32, 0, 0, 32.7, 32.7)
        else ctx.drawImage(sheet!, col * T, capY, 32, 32, 0, 0, 32.7, 32.7)
        ctx.fillStyle = 'rgba(255,240,220,0.16)'
        ctx.fillRect(0, 0, 32.7, 32.7)
      }
      if (dim) {
        ctx.setTransform(S, S / 2, -S, S / 2, S * px, S * (py - h))
        ctx.fillStyle = 'rgba(8,6,14,0.62)'
        ctx.fillRect(0, 0, 32.7, 32.7)
      }
      ctx.restore()
    },
  }
}

