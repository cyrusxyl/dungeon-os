// Checks for lib/blockMap.ts: the heights of blocks, which cells touch, and which blocks fade in front of a figure.
// Run: node stage/web/check/blocks.check.ts (Node 22.18+ strips the types).
import { blockMap, fadedBlocks, isBlock } from '../src/lib/blockMap.ts'

let failed = 0
const check = (label: string, ok: boolean, detail = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}${ok || !detail ? '' : `  (${detail})`}`)
  if (!ok) failed++
}

const props = [
  { kind: 'block_low', x: 2, y: 2 },
  { kind: 'block_half', x: 3, y: 2 },
  { kind: 'block_tall', x: 8, y: 6 },
  { kind: 'barrel', x: 5, y: 5 },
]
const map = blockMap(props)
check('only block kinds count', isBlock('block_tall') && !isBlock('barrel') && map.height.size === 3)
check('a height in px for each kind', map.height.get('2,2') === 14 && map.height.get('3,2') === 28 && map.height.get('8,6') === 48)
check('cells that touch are one block, with one tint', map.tint.get('2,2') === map.tint.get('3,2'))
check('the tint is a small number', [...map.tint.values()].every((t) => Number.isInteger(t) && t >= 0 && t < 4))

// A figure at (7, 5): the tall block at (8, 6) is in front of it (down and right on the screen). A low block does not hide.
check('a tall block in front of a figure fades', fadedBlocks(map, [[7, 5]]).has('8,6'))
check('a figure far away fades nothing', fadedBlocks(map, [[0, 0]]).size === 0)
check('a low block never fades', !fadedBlocks(map, [[1, 1]]).has('2,2'))
check('a half block in front fades, a low one next to it does not', fadedBlocks(map, [[2, 1]]).has('3,2') && !fadedBlocks(map, [[2, 1]]).has('2,2'))
check('a block behind a figure does not fade', !fadedBlocks(map, [[9, 7]]).has('8,6'))

if (failed) {
  console.log(`\n${failed} failed`)
  process.exit(1)
}
console.log('\nall passed')
