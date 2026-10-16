// Checks for lib/dice.ts and lib/traySim.ts. Run: node stage/web/check/dice.check.ts (Node 22.18+ strips the types).
import { diceFor, facing, labelsOf, poseAt, randomSpin, restingPose, tumble, type Kind } from '../src/lib/dice.ts'
import { HZ, simulate, turnLeft } from '../src/lib/traySim.ts'

let failed = 0
const check = (label: string, ok: boolean, detail = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}${ok || !detail ? '' : `  (${detail})`}`)
  if (!ok) failed++
}

const KINDS: Kind[] = ['d4', 'd6', 'd8', 'd10', 'd10t', 'd12', 'd20']
const COUNT: Record<Kind, number> = { d4: 4, d6: 6, d8: 8, d10: 10, d10t: 10, d12: 12, d20: 20 }
for (const k of KINDS) {
  const labels = labelsOf(k)
  check(`${k}: ${COUNT[k]} different labels`, labels.length === COUNT[k] && new Set(labels).size === COUNT[k], labels.join(','))
  const wrong = labels.filter((l) => facing(k, restingPose(k, l)) !== l)
  check(`${k}: every label rests toward the camera`, wrong.length === 0, wrong.join(','))
  const spin = randomSpin()
  const end = labels.filter((l) => facing(k, tumble(k, l, 1, spin)) !== l || facing(k, poseAt(k, l, 0, spin)) !== l)
  check(`${k}: a tumble ends on its label`, end.length === 0, end.join(','))
}
const names = (sides: number, v: number) => diceFor(sides, v).map((d) => `${d.kind}:${d.label}`).join(' ')
check('a d10 shows 10 as 0', names(10, 10) === 'd10:0' && names(10, 7) === 'd10:7')
check('a d100 is a tens die and a units die', names(100, 47) === 'd10t:40 d10:7' && names(100, 100) === 'd10t:00 d10:0' && names(100, 5) === 'd10t:00 d10:5')
check('a die the game has no shape for gives nothing', names(7, 3) === '')

// The throw: from 1 to 40 dice, narrow and wide boxes, many seeds.
const CAP = 2 * 1.0 + 0.3
let bad = 0, runs = 0, slowest = 0
const ends: number[] = []
for (const [n, W, H, size] of [[1, 380, 150, 56], [3, 380, 150, 56], [8, 380, 150, 44], [12, 340, 150, 36], [30, 380, 150, 28], [40, 380, 200, 28], [40, 280, 260, 28]])
  for (let seed = 1; seed <= 60; seed++) {
    const r = 0.42 * size, per = Math.max(1, Math.floor((W - 20) / (size + 6)))
    const starts = Array.from({ length: n }, (_, i) => ({ x: 10 + size / 2 + (i % per) * (size + 6), y: 10 + size / 2 + Math.floor(i / per) * (size + 4) }))
    const H2 = Math.max(H, starts[n - 1].y + size / 2 + 10)
    const t = simulate(starts, r, W, H2, seed)
    runs++; ends.push(t.end); slowest = Math.max(slowest, t.end)
    let ok = t.end < CAP - 1 / HZ
    for (let i = 0; i < n && ok; i++) {
      const x = t.frames[(t.N * n + i) * 2], y = t.frames[(t.N * n + i) * 2 + 1]
      if (x < r - 1e-3 || x > W - r + 1e-3 || y < r - 1e-3 || y > H2 - r + 1e-3 || turnLeft(t, i, t.N) !== 0) ok = false
      for (let j = i + 1; j < n; j++) if (Math.hypot(x - t.frames[(t.N * n + j) * 2], y - t.frames[(t.N * n + j) * 2 + 1]) < 2 * r - 0.5) ok = false
    }
    if (!ok) bad++
  }
ends.sort((a, b) => a - b)
check(`${runs} throws: every die stops, none overlap, none leave the box, every turn ends at 0`, bad === 0, `${bad} bad`)
check('the median throw takes about 1.3 s and none takes more than 2 s', Math.abs(ends[ends.length >> 1] - 1.34) < 0.25 && slowest < 2, `median ${ends[ends.length >> 1].toFixed(2)}, slowest ${slowest.toFixed(2)}`)
const a = simulate([{ x: 30, y: 30 }, { x: 80, y: 30 }], 12, 300, 150, 5), b = simulate([{ x: 30, y: 30 }, { x: 80, y: 30 }], 12, 300, 150, 5)
check('the same seed gives the same throw', a.N === b.N && a.frames.every((v, i) => v === b.frames[i]))

console.log(failed ? `\n${failed} failed` : '\nall passed')
process.exit(failed ? 1 : 0)
