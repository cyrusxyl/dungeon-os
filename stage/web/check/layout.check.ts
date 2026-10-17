// Checks for lib/layout.ts. Run: node stage/web/check/layout.check.ts (Node 22.18+ strips the types).
import { layout, MAX_ACTORS, type ActorState, type StandSpot } from '../src/lib/layout.ts'

let failed = 0
const check = (label: string, ok: boolean, detail = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}${ok || !detail ? '' : `  (${detail})`}`)
  if (!ok) failed++
}

// 12 actors: 4 party, 4 neutral, 4 hostile. The old fold put all but five at `center`.
const twelve: Record<string, ActorState> = {}
for (const [i, side] of (['party', 'party', 'party', 'party', 'ally', 'ally', 'neutral', 'neutral', 'hostile', 'hostile', 'hostile', 'hostile'] as const).entries()) {
  twelve[`a${i}`] = { side, position: 'center' }
}
const cast = layout(twelve)
const spot = (p: { x: number; y: number }) => `${p.x},${p.y}`
check('every actor is placed', cast.length === MAX_ACTORS)
check('no two actors stand on the same spot', new Set(cast.map(spot)).size === cast.length, cast.map(spot).join(' '))
check('all stand inside the stage', cast.every((p) => p.x >= 32 && p.x <= 288))
check('the party stands left of the hostile', Math.max(...cast.filter((p) => p.side !== 'hostile' && p.side !== 'neutral').map((p) => p.x)) < Math.min(...cast.filter((p) => p.side === 'hostile').map((p) => p.x)))
check('drawn back to front', cast.every((p, i) => i === 0 || cast[i - 1].y <= p.y))
check('the party faces right and the hostile left', cast.filter((p) => p.side === 'party').every((p) => p.facing === 'right') && cast.filter((p) => p.side === 'hostile').every((p) => p.facing === 'left'))

const alone = layout({ gareth: { side: 'neutral' } })
check('one neutral NPC stands at the back, in the middle', alone[0].x === 160 && alone[0].y === 122)
const talk = layout({ sireth: { side: 'party' }, gareth: { side: 'neutral' } })
check('a neutral stands beside the party when no one opposes it, and faces it', talk.find((p) => p.id === 'gareth')!.x > talk.find((p) => p.id === 'sireth')!.x && talk.find((p) => p.id === 'gareth')!.facing === 'left')
check('a missing side is neutral', layout({ x: {} })[0].side === 'neutral')

const stand: StandSpot[] = [
  { slot: 'back_center', prop: 'throne', mode: 'sit', points: [[160, 108]] },
  { slot: 'mid_center', prop: 'bench_long', mode: 'sit', points: [[100, 140], [128, 140]] },
]
const on = layout({ arbiter: { side: 'neutral', on: 'back_center' }, a: { on: 'mid_center' }, b: { on: 'mid_center' }, c: { on: 'mid_center' }, d: { on: 'nowhere' } }, stand)
const get = (id: string) => on.find((p) => p.id === id)!
check('an actor on a prop stands on its point, seated', get('arbiter').x === 160 && get('arbiter').y === 108 && get('arbiter').sit)
check('the next actor on the same prop takes the next point', get('a').x === 100 && get('b').x === 128)
check('an actor with no point left stands on the floor', !get('c').onProp && !get('c').sit)
check('an unknown slot is the floor too', !get('d').onProp)
const crowd = layout({ arbiter: { side: 'neutral', on: 'back_center' }, a: { side: 'neutral' }, b: { side: 'neutral' }, c: { side: 'neutral' } }, stand)
const seated = crowd.find((p) => p.id === 'arbiter')!
check('no floor actor stands in front of someone on a prop', crowd.filter((p) => !p.onProp).every((p) => Math.abs(p.x - seated.x) >= 26), crowd.map((p) => p.x).join(' '))
check('a scene with no stand points does not place anyone on a prop', layout({ x: { on: 'back_center' } }, [])[0].onProp === false)

console.log(failed ? `\n${failed} failed` : '\nall passed')
process.exit(failed ? 1 : 0)
