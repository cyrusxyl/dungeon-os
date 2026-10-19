// A stand-in for the game server, for the demo page. The page, the pictures and every component are the real game build.
// What came from the real server (tests/capture_demo.py): the state, the party, the board, the hand, the pictures.
// What is made here: the answers to a move, an attack and an end of turn, with the same rules of the board
// (5 ft straight, 7 ft diagonal, reach and range), and the goblins' turns. There is no DM and no voice.
/* eslint-disable @typescript-eslint/no-explicit-any */
import fixtures from './fixtures.json'

const F: any = fixtures
const ARENA: string = F.arena
const json = (v: unknown) => new Response(JSON.stringify(v), { status: 200, headers: { 'Content-Type': 'application/json' } })
const fromB64 = (b64: string) => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))
const decode = (k: string) => (F.urls[k] ? JSON.parse(new TextDecoder().decode(fromB64(F.urls[k].b64))) : null)

// ---- what this browser remembers: the real choices, plus the board shown on a phone ----
for (const [k, val] of Object.entries(F.storage as Record<string, string>)) localStorage.setItem(k, val)
localStorage.setItem('dungeon-view', 'player')
localStorage.setItem('dungeon-hand', JSON.stringify({ scene: true, layout: 'auto' }))

// ---- pictures: `/asset/...` is answered from the recording ----
const dataUrl = (path: string): string | null => {
  const hit = F.urls[path]
  return hit ? `data:${hit.mime};base64,${hit.b64}` : null
}
const srcSetter = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, 'src')!
Object.defineProperty(HTMLImageElement.prototype, 'src', {
  ...srcSetter,
  set(v: string) {
    srcSetter.set!.call(this, typeof v === 'string' && v.startsWith('/asset/') ? (dataUrl(v) ?? '') : v)
  },
})
const setAttr = Element.prototype.setAttribute
Element.prototype.setAttribute = function (name: string, value: string) {
  if (this instanceof HTMLImageElement && name === 'src') return void ((this as any).src = value)
  return setAttr.call(this, name, value)
}

// ---- the game, in memory ----
const state: any = structuredClone(F.snapshot.state)
const campaign: string = F.snapshot.campaign
const view: any = decode(`/api/arena/${ARENA}`)
const party: any = decode('/api/party')
const handBase: any = decode('/api/arena/hand?who=aragorn')
const blocked = new Set<string>(F.blocked.map((c: number[]) => c.join(',')))
const key = (x: number, y: number) => `${x},${y}`
const cheb = (a: number[], b: number[]) => Math.max(Math.abs(a[0] - b[0]), Math.abs(a[1] - b[1]))
const rnd = (n: number) => 1 + Math.floor(Math.random() * n)
const unit = (id: string) => view.units.find((u: any) => u.id === id)
const pcs = () => view.units.filter((u: any) => u.pc)
const foes = () => view.units.filter((u: any) => !u.pc && !u.down)
const HP: Record<string, { cur: number; max: number }> = { 'goblin#1': { cur: 7, max: 7 }, 'goblin#2': { cur: 7, max: 7 } }
const turn = { action: false, bonus: false, reaction: false }
let feet = 30
let busy = false

const band = (h: { cur: number; max: number }) => (h.cur <= 0 ? 'down' : h.cur <= h.max * 0.25 ? 'near death' : h.cur <= h.max * 0.5 ? 'bloodied' : h.cur < h.max ? 'injured' : 'unhurt')

/** Where a creature can walk: feet by cell. A diagonal step needs both side cells free of walls; no one passes through another. */
function reach(from: number[], limit: number, skip: string) {
  const taken = new Set<string>(view.units.filter((u: any) => u.id !== skip && !u.down).map((u: any) => key(u.x, u.y)))
  const dist = new Map<string, number>([[key(from[0], from[1]), 0]])
  const prev = new Map<string, string>()
  const open: [number, number, number][] = [[from[0], from[1], 0]]
  while (open.length) {
    open.sort((a, b) => a[2] - b[2])
    const [x, y, d] = open.shift()!
    if (d > (dist.get(key(x, y)) ?? Infinity)) continue
    for (let dx = -1; dx <= 1; dx++)
      for (let dy = -1; dy <= 1; dy++) {
        if (!dx && !dy) continue
        const n = [x + dx, y + dy]
        const k = key(n[0], n[1])
        if (n[0] < 0 || n[1] < 0 || n[0] >= view.w || n[1] >= view.h || blocked.has(k) || taken.has(k)) continue
        if (dx && dy && (blocked.has(key(x + dx, y)) || blocked.has(key(x, y + dy)))) continue
        const nd = d + (dx && dy ? 7 : 5)
        if (nd > limit || nd >= (dist.get(k) ?? Infinity)) continue
        dist.set(k, nd)
        prev.set(k, key(x, y))
        open.push([n[0], n[1], nd])
      }
  }
  return { dist, prev }
}
const pathTo = (prev: Map<string, string>, from: number[], to: number[]) => {
  const out: number[][] = []
  let cur = key(to[0], to[1])
  while (cur !== key(from[0], from[1])) {
    out.unshift(cur.split(',').map(Number))
    cur = prev.get(cur)!
  }
  return out
}

function refreshWalk() {
  const cur = unit(view.current)
  if (cur?.pc && !busy) {
    const { dist } = reach([cur.x, cur.y], feet, cur.id)
    view.walk = [...dist].filter(([, d]) => d > 0).map(([k]) => k.split(',').map(Number))
    view.feet_left = feet
  } else {
    view.walk = []
    view.feet_left = 0
  }
}

/** The hand of the character on turn: the recorded cards, with targets, reach and the used action worked out again. */
function makeHand() {
  const me = unit('aragorn')
  const hand = structuredClone(handBase)
  hand.turn = { ...turn }
  hand.feet_left = feet
  hand.current = view.current
  for (const ab of hand.abilities) {
    const used = ab.cost === 'action' ? turn.action : ab.cost === 'bonus' ? turn.bonus : false
    ab.why = view.current !== 'aragorn' ? 'Not your turn.' : used ? `The ${ab.cost} is used.` : null
    if (ab.kind === 'attack' || ab.kind === 'shove') {
      ab.targets = foes().map((f: any) => {
        const ft = cheb([me.x, me.y], [f.x, f.y]) * 5
        const reachFt = ab.kind === 'shove' ? 5 : (ab.entry.reach_ft ?? ab.entry.range_ft)
        const ok = ft <= reachFt
        const chance = Math.max(0.05, Math.min(0.95, (21 - (15 - (ab.entry?.bonus ?? 0))) / 20))
        return { id: f.id, name: f.name, dist_ft: ft, ok, why: ok ? null : ab.entry?.range_ft ? `${f.id} is ${ft} ft away.` : `${f.id} is ${ft} ft away. Walk next to it: ${ab.name} reaches ${reachFt} ft.`, ...(ok && ab.kind === 'attack' ? { odds: chance >= 0.65 ? 'good odds' : chance >= 0.35 ? 'even odds' : 'poor odds' } : {}) }
      })
    }
  }
  return hand
}

function syncParty() {
  const ar = party.characters.find((c: any) => c.id === 'aragorn')
  const u = unit('aragorn')
  ar.hp.current = u.hp.current
  ar.turn = { ...turn }
  party.combat.round = view.round
  party.combat.current = view.current
  for (const o of party.combat.order) {
    const v = unit(o.id)
    o.health = v.pc ? (v.hp.current <= 0 ? 'down' : 'unhurt') : v.health
  }
  const ac = party.characters.find((c: any) => c.id === 'legolas')
  ac.hp.current = unit('legolas').hp.current
}

// ---- telling the page: a new snapshot, as the real server does after a change ----
const sockets = new Set<any>()
let seq = state.seq + 100
const send = () => {
  for (const s of sockets) s.onmessage?.({ data: JSON.stringify({ kind: 'snapshot', state, campaign }) })
}
function publish() {
  refreshWalk()
  syncParty()
  seq += 1
  state.seq = seq
  state.versions[`arena:${ARENA}`] = seq
  send()
}
function addRoll(roll: any) {
  seq += 1
  state.rolls = [...state.rolls, { ...roll, seq }]
  state.feed = [...state.feed, { seq, text: roll.expr }]
}

// ---- rolls, in the shape the real engine logs ----
function rollDice(expr: string, crit: boolean) {
  const m = /^(\d+)d(\d+)([+-]\d+)?$/.exec(expr)!
  const n = Number(m[1]) * (crit ? 2 : 1)
  const faces = Array.from({ length: n }, () => rnd(Number(m[2])))
  const bonus = Number(m[3] ?? 0)
  return { faces, total: faces.reduce((a, b) => a + b, 0) + bonus, die: `${n}d${m[2]}` }
}

function resolveAttack(att: any, target: any, ac: number, weapon: { name: string; bonus: number; expr: string; type: string }) {
  const d20 = rnd(20)
  const total = d20 + weapon.bonus
  const outcome = d20 === 20 ? 'crit' : d20 === 1 ? 'fumble' : total >= ac ? 'hit' : 'miss'
  const hit = outcome === 'hit' || outcome === 'crit'
  const dmg = hit ? rollDice(weapon.expr, outcome === 'crit') : null
  const detail: any = {
    kind: 'attack',
    title: weapon.name,
    subtitle: `Attack Roll · ${att.name} → ${target.name}`,
    ...(att.pc ? {} : { target: { label: 'Armor Class', value: ac } }), // a hero never sees a creature's AC; a creature's attack shows the hero's
    rolls: [{ who: att.id, name: att.name, d20: [d20], kept: 0, mode: 'normal', mods: [{ label: 'Attack Bonus', value: weapon.bonus }], bonus: [], total, outcome }],
    ...(dmg ? { damage: [{ type: weapon.type, expr: weapon.expr, faces: dmg.faces, groups: [{ die: dmg.die, faces: dmg.faces }], total: dmg.total }] } : {}),
  }
  addRoll({ expr: `${att.name}: ${weapon.name}${dmg ? ` — ${dmg.total} ${weapon.type} damage` : ''}`, total: dmg ? dmg.total : total, dice: [{ die: '1d20', faces: [d20] }, ...(dmg ? [{ die: dmg.die, faces: dmg.faces }] : [])], detail })
  return { hit, damage: dmg?.total ?? 0 }
}

function hurt(target: any, amount: number) {
  if (target.pc) {
    target.hp.current = Math.max(0, target.hp.current - amount)
    target.health = target.hp.current <= 0 ? 'down' : 'unhurt'
  } else {
    const h = HP[target.id]
    h.cur = Math.max(0, h.cur - amount)
    target.health = band(h)
    target.down = h.cur <= 0
    if (target.down) target.intent = undefined
  }
}

// ---- what the player does ----
function walkTo(u: any, to: number[], limit: number) {
  const { dist, prev } = reach([u.x, u.y], limit, u.id)
  const d = dist.get(key(to[0], to[1]))
  if (d === undefined || d === 0) return null
  const cells = pathTo(prev, [u.x, u.y], to)
  const trail = view.trails[u.id]?.length && key(...(view.trails[u.id].at(-1) as [number, number])) === key(u.x, u.y) ? view.trails[u.id] : [[u.x, u.y]]
  view.trails[u.id] = [...trail, ...cells].slice(-40)
  u.x = to[0]
  u.y = to[1]
  return { cells, feet: d }
}

function playerAttack(targetId: string, weaponName?: string) {
  const me = unit('aragorn')
  const target = unit(targetId)
  if (!target || target.down) return { error: 'Pick a target on the board.' }
  if (turn.action) return { error: 'The action is used.' }
  const ft = cheb([me.x, me.y], [target.x, target.y]) * 5
  const weapons: any = { Longsword: { name: 'Longsword', bonus: 5, expr: '1d8+3', type: 'slashing', reach: 5 }, Longbow: { name: 'Longbow', bonus: 4, expr: '1d8+2', type: 'piercing', reach: 150 }, 'Unarmed Strike': { name: 'Unarmed Strike', bonus: 5, expr: '1d1+3', type: 'bludgeoning', reach: 5 } }
  const w = weapons[weaponName ?? (ft <= 5 ? 'Longsword' : 'Longbow')]
  if (ft > w.reach) return { error: `${targetId} is ${ft} ft away. Walk next to it: ${w.name} reaches ${w.reach} ft.` }
  turn.action = true
  const out = resolveAttack(me, target, 15, w)
  if (out.hit) hurt(target, out.damage)
  if (!foes().length) state.feed = [...state.feed, { seq: ++seq, text: 'Every goblin is down.' }]
  publish()
  return { lines: [] }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

async function endTurn() {
  if (busy) return
  busy = true
  const next = (id: string) => {
    view.current = id
    publish()
  }
  next('legolas')
  await sleep(900)
  for (const g of ['goblin#1', 'goblin#2']) {
    const gob = unit(g)
    if (!gob || gob.down) continue
    next(g)
    await sleep(900)
    const alive = pcs().filter((p: any) => p.hp.current > 0)
    if (!alive.length) break
    const near = (p: any) => cheb([gob.x, gob.y], [p.x, p.y])
    let target = alive.reduce((a: any, b: any) => (near(a) <= near(b) ? a : b))
    if (near(target) > 1) {
      const { dist, prev } = reach([gob.x, gob.y], 30, g)
      const goal = [...dist.keys()].map((k) => k.split(',').map(Number)).reduce((best, c) => (cheb(c, [target.x, target.y]) < cheb(best, [target.x, target.y]) || (cheb(c, [target.x, target.y]) === cheb(best, [target.x, target.y]) && (dist.get(key(c[0], c[1])) ?? 0) < (dist.get(key(best[0], best[1])) ?? 0)) ? c : best))
      if (key(goal[0], goal[1]) !== key(gob.x, gob.y)) {
        const cells = pathTo(prev, [gob.x, gob.y], goal)
        view.trails[g] = [...(view.trails[g] ?? [[gob.x, gob.y]]), ...cells].slice(-40)
        gob.x = goal[0]
        gob.y = goal[1]
        publish()
        await sleep(300 + cells.length * 230)
      }
      target = alive.reduce((a: any, b: any) => (near(a) <= near(b) ? a : b))
    }
    if (near(target) <= 1) {
      const out = resolveAttack(gob, target, target.id === 'aragorn' ? 16 : 15, { name: 'Scimitar', bonus: 4, expr: '1d6+2', type: 'slashing' })
      if (out.hit) hurt(target, out.damage)
      publish()
      await sleep(3600)
    }
  }
  view.round += 1
  turn.action = turn.bonus = turn.reaction = false
  feet = 30
  busy = false
  next('aragorn')
}

async function handle(path: string, body: any): Promise<Response> {
  const bad = (error: string) => new Response(JSON.stringify({ error }), { status: 400, headers: { 'Content-Type': 'application/json' } })
  if (path === '/api/arena/move') {
    const me = unit(body.who)
    if (view.current !== body.who) return bad(`It is ${view.current}'s turn, not ${body.who}'s.`)
    const out = walkTo(me, body.to, feet)
    if (!out) return bad(`${body.who} cannot reach ${body.to[0]},${body.to[1]}: ${feet} ft of walking left.`)
    feet -= out.feet
    publish()
    return json({ steps: out.cells, lines: [], pending: null })
  }
  if (path === '/api/arena/attack') {
    const out: any = playerAttack(body.target)
    return out.error ? bad(out.error) : json(out)
  }
  if (path === '/api/arena/act') {
    const id: string = body.ability
    if (id.startsWith('attack:')) {
      const out: any = playerAttack(body.target, id.slice(7))
      return out.error ? bad(out.error) : json(out)
    }
    const ab = handBase.abilities.find((a: any) => a.id === id)
    if (!ab) return bad(`no ability ${id}.`)
    if (ab.cost === 'action' && turn.action) return bad('The action is used.')
    if (ab.cost === 'bonus' && turn.bonus) return bad('The bonus action is used.')
    if (ab.cost === 'action') turn.action = true
    if (ab.cost === 'bonus') turn.bonus = true
    if (id === 'dash') feet += 30
    publish()
    return json({ lines: [] })
  }
  if (path === '/api/end-turn') {
    void endTurn()
    return json({ ok: true })
  }
  if (path === '/api/combat/settings') {
    state.combat_settings = { ...state.combat_settings, ...body }
    view.settings = { ...state.combat_settings }
    publish()
    return json(state.combat_settings)
  }
  return json({ ok: true })
}

// ---- the network ----
const realFetch = window.fetch.bind(window)
window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const raw = typeof input === 'string' ? input : input instanceof URL ? input.pathname + input.search : input.url
  const path = raw.replace(location.origin, '')
  if (!path.startsWith('/api/') && !path.startsWith('/asset/')) return realFetch(input, init)
  if ((init?.method ?? 'GET') === 'POST') {
    let body: any = {}
    try {
      body = JSON.parse(String(init?.body ?? '{}'))
    } catch {
      /* no body */
    }
    return handle(path.split('?')[0], body)
  }
  if (path === `/api/arena/${ARENA}`) return json(view)
  if (path === '/api/party') return json(party)
  if (path.startsWith('/api/arena/hand')) return json(makeHand())
  const hit = F.urls[path]
  if (hit) return new Response(fromB64(hit.b64), { status: 200, headers: { 'Content-Type': hit.mime } })
  return path.startsWith('/asset/') ? new Response('', { status: 404 }) : json({})
}

class FakeSocket {
  onopen: any = null
  onmessage: any = null
  onclose: any = null
  readyState = 0
  static OPEN = 1
  constructor(url: string) {
    if (url.includes('/pty')) return
    sockets.add(this)
    setTimeout(() => {
      this.readyState = 1
      this.onopen?.({})
      this.onmessage?.({ data: JSON.stringify({ kind: 'snapshot', state, campaign }) })
    }, 0)
  }
  send() {}
  close() {
    sockets.delete(this)
  }
}
;(window as any).WebSocket = FakeSocket

// The page starts with the board as the capture left it, with no roll to play.
refreshWalk()
syncParty()
view.round = view.round ?? 1
