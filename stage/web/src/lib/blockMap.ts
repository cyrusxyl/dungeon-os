// The maths of blocks that needs no canvas: heights, which cells touch, which blocks fade (stage/blocks.py is the server side).
// Pure, so a check can run it (check/blocks.check.ts).

/** The height drawn for each kind, in px (the same as PIXELS in stage/blocks.py). */
export const BLOCK_PX: Record<string, number> = { block_low: 14, block_half: 28, block_tall: 48, block_pillar: 64 }
export const isBlock = (kind: string): boolean => kind in BLOCK_PX

/** A block this high or higher hides a figure behind it. */
const HIDES = 28
/** The cells in front of a figure, on the screen, where a block may cover it. */
const FRONT: [number, number][] = [[1, 0], [0, 1], [1, 1], [2, 1], [1, 2], [2, 2], [2, 0], [0, 2]]

export interface BlockMap {
  /** The height of each block cell, by `x,y`. */
  height: Map<string, number>
  /** Which block each cell belongs to (cells that touch are one block), as a small number: it picks the color. */
  tint: Map<string, number>
}

/** The block cells among the props of a room, with their heights and their blocks. */
export function blockMap(props: { kind: string; x: number; y: number }[]): BlockMap {
  const height = new Map<string, number>()
  for (const p of props) if (isBlock(p.kind)) height.set(`${p.x},${p.y}`, BLOCK_PX[p.kind])
  const tint = new Map<string, number>()
  for (const key of [...height.keys()].sort()) {
    if (tint.has(key)) continue
    const [x0, y0] = key.split(',').map(Number)
    const label = (x0 * 7 + y0 * 3) % 4
    const stack = [key]
    tint.set(key, label)
    while (stack.length) {
      const [x, y] = stack.pop()!.split(',').map(Number)
      for (const n of [`${x + 1},${y}`, `${x - 1},${y}`, `${x},${y + 1}`, `${x},${y - 1}`]) {
        if (height.has(n) && !tint.has(n)) {
          tint.set(n, label)
          stack.push(n)
        }
      }
    }
  }
  return { height, tint }
}

/** The block cells that cover a figure now: a block of 28 or more in front of it fades. `figures` are cells. */
export function fadedBlocks(map: BlockMap, figures: [number, number][]): Set<string> {
  const out = new Set<string>()
  for (const [x, y] of figures) {
    for (const [dx, dy] of FRONT) {
      const key = `${x + dx},${y + dy}`
      if ((map.height.get(key) ?? 0) >= HIDES) out.add(key)
    }
  }
  return out
}
