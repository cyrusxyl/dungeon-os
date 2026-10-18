import { useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/8bit/button'
import { Hand } from '@/components/Hand'
import type { Ability, ArenaUnit, ArenaView as View, Cell, Preview } from '@/lib/arena'
import { useHand, useSkin } from '@/lib/hand'
import { buildBase, byDepth, diamond, facing, frameAt, geometry, groundCentre, pick as pickCell, roomCentre, S, unitDepth, type Base, type Facing, type Geometry, type Style } from '@/lib/iso'
import { type PropsInfo, usePropsInfo } from '@/lib/propAtlas'
import { propThing, sceneBase, sceneStyle, type Thing } from '@/lib/roomDraw'
import { BAND_FILL } from '@/lib/party'
import { deviceHeaders, postJson, type StageState, useFitScale, useJson } from '@/lib/stage'
import { T, useImages, variant, type ImageLoader } from '@/lib/tiles'


/** What a unit looked like last time: where it stood, which way it faces, and the last picture that loaded for that way. */
type Seen = { x: number; y: number; face: Facing; img?: HTMLImageElement }

const WALK = 'rgba(95, 168, 224, 0.16)'
const WALK_EDGE = 'rgba(95, 168, 224, 0.55)'
const AIM_OK = 'rgba(224, 90, 60, 0.28)'
const AIM_NO = 'rgba(120, 120, 120, 0.22)'

const inside = (view: View, x: number, y: number) => x >= 0 && y >= 0 && x < view.w && y < view.h
const seenNow = (view: View, x: number, y: number) => !view.visible || view.visible[y]?.[x] === '1'

/** The part of the room that does not move: floor and back walls. It is rebuilt only when the room or the fog changes. */
function baseFor(prev: { sig: string; base: Base } | null, view: View, g: Geometry, image: ImageLoader, props: PropsInfo | undefined, atlas: HTMLImageElement | undefined): { sig: string; base: Base } {
  const scene = view.room
  const tiles = image(scene ? `/asset/arena/${view.id}/room.png` : `/asset/arena/${view.id}.png`)
  const hazard = image(`/asset/icon/${view.hazard}.png`)
  const sig = [view.id, view.grid.join('|'), view.visible?.join('|') ?? '', tiles ? 1 : 0, hazard ? 1 : 0, scene && props && atlas ? 1 : 0].join('#')
  if (prev?.sig === sig) return prev
  const tex = (col: number, row: number) => (tiles ? { img: tiles, sx: col * T, sy: row * T } : undefined)
  const extra: Partial<Style> = {
    floorOver: (_x, _y, c) => (c === 'd' ? tex(1, 2) : c === '~' && hazard ? { img: hazard, sx: 0, sy: 0 } : undefined),
    dim: view.visible ? (x, y) => view.grid[y][x] !== ' ' && view.visible![y][x] === '0' : undefined,
  }
  if (scene) return { sig, base: sceneBase(scene, view.grid, g, sceneStyle(scene, tiles, extra), props, atlas) }
  const style: Style = {
    floor: (x, y) => tex(view.tiles.pattern ? (x % 2) + (y % 2) * 2 : variant(x, y, view.tiles.floors), 1),
    wall: (x, y) => tex(variant(x, y, view.tiles.walls), 0),
    ...extra,
  }
  return { sig, base: buildBase(g, view.grid, style) }
}

function unitFace(seen: Map<string, Seen>, u: ArenaUnit): Seen {
  const was = seen.get(u.id)
  if (!was) return { x: u.x, y: u.y, face: 'down' }
  if (was.x === u.x && was.y === u.y) return was
  return { ...was, x: u.x, y: u.y, face: facing(u.x - was.x, u.y - was.y) }
}

/** The ring under the feet: green for the party's side, yellow for a faction at peace with it (and for a bystander), red for an enemy. */
const RING = { party: '#5fd08a', neutral: '#e8c14a', hostile: '#ef6a5a' } as const

function ring(ctx: CanvasRenderingContext2D, cx: number, cy: number, color: string) {
  ctx.fillStyle = color
  ctx.globalAlpha = 0.75
  ctx.strokeStyle = '#0008'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.ellipse(cx, cy, 15, 6, 0, 0, Math.PI * 2)
  ctx.fill()
  ctx.stroke()
  ctx.globalAlpha = 1
}

/** An actor of the scene that takes no part in the fight. */
function drawBystander(ctx: CanvasRenderingContext2D, g: Geometry, b: { id: string; x: number; y: number }, image: ImageLoader) {
  const [cx, cy] = groundCentre(g, b.x, b.y)
  ctx.setTransform(S, 0, 0, S, 0, 0)
  ring(ctx, cx, cy, RING.neutral)
  const img = image(`/asset/actor/${encodeURIComponent(b.id)}/full.png?d=down`)
  if (img) {
    const [fx, fy] = frameAt(g, b.x, b.y, img.width, img.height)
    ctx.drawImage(img, fx, fy)
  }
}

function drawUnit(ctx: CanvasRenderingContext2D, g: Geometry, u: ArenaUnit, image: ImageLoader, seen: Map<string, Seen>) {
  const now = unitFace(seen, u)
  const url = (f: Facing) => `/asset/actor/${encodeURIComponent(u.id)}/full.png?d=${f}`
  const img = image(url(now.face)) ?? now.img // while a new facing loads, keep the last picture
  seen.set(u.id, { ...now, img: img ?? now.img })
  const [cx, cy] = groundCentre(g, u.x, u.y)
  ctx.setTransform(S, 0, 0, S, 0, 0)
  if (!u.down) ring(ctx, cx, cy, RING[u.team])
  ctx.globalAlpha = u.down ? 0.35 : 1
  if (img) {
    const [fx, fy] = frameAt(g, u.x, u.y, img.width, img.height)
    ctx.drawImage(img, fx, fy)
  } else {
    ctx.fillStyle = u.pc ? '#5fa8e0' : '#e5534f'
    ctx.beginPath()
    ctx.ellipse(cx, cy - 10, 9, 12, 0, 0, Math.PI * 2)
    ctx.fill()
    ctx.fillStyle = '#000'
    ctx.font = 'bold 12px sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText(u.name.charAt(0), cx, cy - 6)
  }
  ctx.globalAlpha = 1
}

/** Health bar and intent label, drawn after all sprites so that a unit in front never covers them. */
function drawMarks(ctx: CanvasRenderingContext2D, g: Geometry, u: ArenaUnit, seen: Map<string, Seen>) {
  const [cx, cy] = groundCentre(g, u.x, u.y)
  ctx.setTransform(S, 0, 0, S, 0, 0)
  if (u.intent && !u.down) {
    const top = cy - Math.max(40, (seen.get(u.id)?.img?.height ?? 64) - 8) - 2
    const text = u.intent.text
    ctx.font = '8px sans-serif'
    ctx.textAlign = 'center'
    const w = Math.min(ctx.measureText(text).width + 6, T * 3)
    ctx.fillStyle = u.intent.kind === 'dm' ? 'rgba(20,50,90,0.85)' : 'rgba(60,10,10,0.85)'
    ctx.fillRect(cx - w / 2, top - 10, w, 10)
    ctx.fillStyle = u.intent.kind === 'move' ? '#c9a96e' : '#ffd6d3'
    ctx.fillText(text, cx, top - 2, T * 3 - 6)
  }
  const fill = u.hp ? (u.hp.current / (u.hp.max || 1)) * 100 : BAND_FILL[u.health]
  ctx.fillStyle = '#000'
  ctx.fillRect(cx - 13, cy + 7, 26, 4)
  ctx.fillStyle = RING[u.team]
  ctx.fillRect(cx - 12, cy + 8, Math.round((24 * fill) / 100), 2)
}

function draw(
  ctx: CanvasRenderingContext2D,
  view: View,
  g: Geometry,
  base: Base,
  hover: Cell | null,
  image: ImageLoader,
  aim: Preview | null,
  props: PropsInfo | undefined,
  atlas: HTMLImageElement | undefined,
  seen: Map<string, Seen>,
) {
  ctx.imageSmoothingEnabled = false
  ctx.setTransform(1, 0, 0, 1, 0, 0)
  ctx.drawImage(base.canvas, 0, 0)

  // Overlays lie on the floor: range, aim area, the creatures an aim covers, the hover and the turn.
  if (!aim) for (const [x, y] of view.walk) diamond(ctx, g, x, y, WALK, WALK_EDGE)
  if (aim) for (const [x, y] of aim.cells) diamond(ctx, g, x, y, aim.ok ? AIM_OK : AIM_NO, aim.ok ? 'rgba(224, 90, 60, 0.7)' : undefined)
  if (aim) for (const u of view.units) if (aim.units.includes(u.id)) diamond(ctx, g, u.x, u.y, undefined, '#ffd24a', 2)
  const current = view.units.find((u) => u.id === view.current)
  if (current) diamond(ctx, g, current.x, current.y, undefined, '#c9a96e', 2)
  if (hover) diamond(ctx, g, hover[0], hover[1], undefined, '#fff', 1)
  ctx.setTransform(S, 0, 0, S, 0, 0)
  ctx.fillStyle = '#7fb2d6'
  for (const item of view.items) {
    const [cx, cy] = groundCentre(g, item.x, item.y)
    ctx.beginPath()
    ctx.ellipse(cx, cy, 5, 3, 0, 0, Math.PI * 2)
    ctx.fill()
  }

  const centre = roomCentre(view.grid)
  // Flat props, the low walls, props and creatures, back to front.
  const things: Thing[] = base.rims.map((r) => ({ depth: r.depth, draw: () => r.draw(ctx) }))
  if (props && atlas) {
    for (const p of view.props) {
      const thing = propThing(ctx, g, props, atlas, p, centre, !seenNow(view, p.x, p.y))
      if (thing) things.push(thing)
    }
  }
  for (const u of view.units) things.push({ depth: unitDepth(u.x, u.y), draw: () => drawUnit(ctx, g, u, image, seen) })
  for (const b of view.bystanders ?? []) things.push({ depth: unitDepth(b.x, b.y), draw: () => drawBystander(ctx, g, b, image) })
  for (const t of byDepth(things)) t.draw()
  for (const u of view.units) drawMarks(ctx, g, u, seen)
}

/** The seconds left to answer a reaction question, counted down on this screen. The server decides when the time is up. */
function Countdown({ from }: { from: number | null }) {
  const [left, setLeft] = useState(from)
  useEffect(() => {
    if (from === null) return
    const id = window.setInterval(() => setLeft((n) => (n === null ? n : Math.max(0, n - 1))), 1000)
    return () => window.clearInterval(id)
  }, [from])
  return left === null ? null : <> ({left})</>
}

const REACTION_TIMES = [0, 5, 10, 20, 30, 60]

/** The host's controls during play: how long a player has to answer a reaction question, and the DM's one beat for each round. */
function CombatSettings({ settings }: { settings: { reaction_seconds: number; round_summary: boolean } }) {
  const set = (body: Record<string, unknown>) => postJson('/api/combat/settings', body)
  const next = REACTION_TIMES[(REACTION_TIMES.indexOf(settings.reaction_seconds) + 1) % REACTION_TIMES.length]
  return (
    <div className="absolute top-2 right-2 flex flex-col items-end gap-1 text-[10px]">
      <Button size="sm" variant="outline" className="text-[10px]" onClick={() => set({ reaction_seconds: next })} title="Time to answer a reaction question (click to change)">
        Reaction time: {settings.reaction_seconds ? `${settings.reaction_seconds} s` : 'no limit'}
      </Button>
      <Button size="sm" variant="outline" className="text-[10px]" onClick={() => set({ round_summary: !settings.round_summary })} title="The DM tells one beat after each round">
        Round summary: {settings.round_summary ? 'on' : 'off'}
      </Button>
      <Button size="sm" variant="outline" className="text-[10px]" onClick={() => set({ ...settings, make_default: true })} title="Keep these for every game on this machine">
        Make default
      </Button>
    </div>
  )
}

/**
 * The board of a fight. The server owns the rules: a click on a blue cell walks, a click on a creature attacks with the
 * weapon that reaches it. A refusal comes back as words ("The goblin is 25 ft away"), which show over the board.
 */
export function ArenaView({ state, arenaId, actingAs, mine, isHost }: { state: StageState; arenaId: string; actingAs: string | null; mine: string[]; isHost: boolean }) {
  const box = useRef<HTMLDivElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const view = useJson<View>(`/api/arena/${encodeURIComponent(arenaId)}`, state.versions?.[`arena:${arenaId}`] ?? 0)
  const g = geometry(view?.w ?? 16, view?.h ?? 10)
  const scale = useFitScale(box, g.width, g.height)
  const [image, tick] = useImages()
  const props = usePropsInfo()
  const atlas = props ? image(props.atlas) : undefined
  const base = useRef<{ sig: string; base: Base } | null>(null)
  const seen = useRef(new Map<string, Seen>())
  const [hover, setHover] = useState<[number, number] | null>(null)
  const [note, setNote] = useState('')
  const busy = useRef(false)
  const canWalk = Boolean(view && actingAs && view.current === actingAs && !view.pending)
  const version = state.versions?.[`arena:${arenaId}`] ?? 0
  const hand = useHand(canWalk ? actingAs : null, version)
  const [skin, flipSkin] = useSkin()
  const [picked, setPicked] = useState<string | null>(null)
  const [ask, setAsk] = useState<{ path: string; body: Record<string, unknown>; why: string } | null>(null)
  const [aim, setAim] = useState<Preview | null>(null)
  // The ability is read from the fresh hand, so its targets and reasons never go stale.
  const selected: Ability | null = hand?.abilities.find((ab) => ab.id === picked && !ab.why) ?? null
  const aimed = selected?.needs === 'aim' ? selected : null
  const aimedId = aimed?.id ?? null

  useEffect(() => {
    const ctx = canvas.current?.getContext('2d')
    if (!ctx || !view) return
    base.current = baseFor(base.current, view, g, image, props, atlas)
    draw(ctx, view, g, base.current.base, hover, image, aimed ? aim : null, props, atlas, seen.current)
  }, [view, hover, image, tick, aim, aimed, props, atlas]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!aimedId || !hover || !actingAs) return
    let live = true
    fetch('/api/arena/preview', { method: 'POST', headers: { 'Content-Type': 'application/json', ...deviceHeaders() }, body: JSON.stringify({ who: actingAs, ability: aimedId, aim: hover }) })
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null)
      .then((p: Preview | null) => live && setAim(p && { ...p, at: hover }))
    return () => {
      live = false
    }
  }, [aimedId, hover, actingAs])
  useEffect(() => {
    if (!note) return
    const id = window.setTimeout(() => setNote(''), 4000)
    return () => window.clearTimeout(id)
  }, [note])

  if (!view) {
    // The same elements as the board below, so that `box` keeps its element (and its size observer) when the board arrives.
    return (
      <div className="flex h-full w-full flex-col">
        <div ref={box} className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden" />
      </div>
    )
  }

  /** The cell under the pointer, or null off the room. */
  const cellAt = (e: React.MouseEvent<HTMLCanvasElement>): Cell | null => {
    const rect = e.currentTarget.getBoundingClientRect()
    const [x, y] = pickCell(g, ((e.clientX - rect.left) / rect.width) * g.width, ((e.clientY - rect.top) / rect.height) * g.height)
    return inside(view, x, y) ? [x, y] : null
  }
  /** A request to the board. An attack that starts a fight with a bystander, or breaks a peace, comes back as a question (409, `confirm`):
   *  it is asked, and sent again with `confirm` when the player agrees. */
  const call = async (path: string, body: Record<string, unknown>) => {
    if (busy.current) return
    busy.current = true
    try {
      const res = await postJson(path, body)
      if (res.status === 409) {
        const asked = (await res.clone().json().catch(() => null)) as { error?: string; confirm?: boolean } | null
        if (asked?.confirm) return setAsk({ path, body, why: asked.error ?? 'This starts a fight.' })
      }
      if (!res.ok) setNote(((await res.json().catch(() => null)) as { error?: string } | null)?.error ?? 'The board refused that.')
    } finally {
      busy.current = false
    }
  }
  const act = async (ab: Ability, target?: string, amount?: number, at?: Cell) => {
    if (!actingAs) return
    await call('/api/arena/act', { who: actingAs, ability: ab.id, target, amount, aim: at })
    setPicked(null)
  }
  const improvise = async (text: string, object?: string) => {
    if (!actingAs) return
    await call('/api/arena/improvise', { who: actingAs, text, object })
    setPicked(null)
  }
  const pick = (ab: Ability) => {
    if (ab.why) return setNote(ab.why)
    if (ab.needs === 'none') act(ab)
    else setPicked(ab.id)
  }
  const click = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!canWalk || !actingAs) return
    const cell = cellAt(e)
    if (!cell) return
    const [x, y] = cell
    if (aimed) {
      // Look before the cast: the first tap on a cell (a phone has no hover) shows what it covers; a tap on the same cell casts.
      if (aim?.at?.[0] === x && aim.at[1] === y && aim.ok) return act(aimed, undefined, undefined, [x, y])
      setHover([x, y])
      return setNote(aim?.at?.[0] === x && aim.at[1] === y ? (aim.why ?? 'You cannot aim there.') : 'Tap the same cell again to cast.')
    }
    const foe = view.units.find((u) => u.team !== 'party' && !u.down && u.x === x && u.y === y) ?? view.bystanders?.find((b) => b.x === x && b.y === y)
    if (foe && selected?.needs === 'target') act(selected, foe.id)
    else if (foe) call('/api/arena/attack', { who: actingAs, target: foe.id })
    else if (view.walk.some(([wx, wy]) => wx === x && wy === y)) call('/api/arena/move', { who: actingAs, to: [x, y] })
    else setNote('You cannot walk there this turn.')
  }
  const asked = view.pending && mine.includes(view.pending.who) ? view.pending : null
  const name = (id: string) => view.units.find((u) => u.id === id)?.name ?? id
  const mover = canWalk ? '' : `${name(view.current ?? '')} `

  return (
    <div className="flex h-full w-full min-w-0 flex-col">
      <div ref={box} className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden">
        <canvas
          ref={canvas}
          width={g.width * S}
          height={g.height * S}
          onClick={click}
          data-geom={`${g.ox},${g.oy},${g.width},${g.height}`}
          onMouseMove={(e) => {
            const cell = cellAt(e)
            setHover((prev) => (prev?.[0] === cell?.[0] && prev?.[1] === cell?.[1] ? prev : cell)) // one redraw per cell crossed
          }}
          onMouseLeave={() => setHover(null)}
          aria-label="The board of the fight. Click a blue cell to walk. Click a creature to attack it."
          className={`pixelated shrink-0 ${canWalk ? 'cursor-pointer' : 'cursor-default'}`}
          style={{ width: g.width * scale, height: g.height * scale }}
        />
        <div className="pointer-events-none absolute top-2 left-2 flex flex-col gap-1">
          <span className="pixel-font bg-black/60 px-2 py-1 text-[10px] text-[var(--gold)]">
            Round {view.round}
            {view.walk.length ? ` · ${mover}${view.feet_left} ft left` : ''}
          </span>
          {note && <span className="pixel-font bg-black/70 px-2 py-1 text-[8px] text-[var(--bad)]">{note}</span>}
        </div>
        {isHost && <CombatSettings settings={state.combat_settings ?? view.settings} />}
        {ask && (
          <div role="alertdialog" className="absolute inset-x-2 bottom-2 flex flex-wrap items-center justify-center gap-2 border-2 border-[var(--border)] bg-black/90 p-2">
            <span className="text-sm">{ask.why}</span>
            <Button size="sm" onClick={() => { const { path, body } = ask; setAsk(null); void call(path, { ...body, confirm: true }) }} className="text-[10px]">
              Attack anyway
            </Button>
            <Button size="sm" variant="outline" onClick={() => setAsk(null)} className="text-[10px]">
              Cancel
            </Button>
          </div>
        )}
        {view.pending && (
          <div className="absolute inset-x-2 bottom-2 flex flex-wrap items-center justify-center gap-2 border-2 border-[var(--border)] bg-black/80 p-2">
            {asked ? (
              <>
                <span className="text-sm">{name(asked.against)} leaves your reach. Take an opportunity attack?</span>
                <Button size="sm" onClick={() => call('/api/arena/react', { take: true })} className="text-[10px]">
                  Attack
                </Button>
                <Button size="sm" variant="outline" onClick={() => call('/api/arena/react', { take: false })} className="text-[10px]">
                  Skip<Countdown key={view.pending?.seconds_left} from={view.pending?.seconds_left ?? null} />
                </Button>
              </>
            ) : (
              <span className="text-sm text-[var(--dim)]">{name(view.pending.who)} decides on a reaction attack…</span>
            )}
          </div>
        )}
      </div>
    {hand && canWalk && <Hand key={hand.who} hand={hand} skin={skin} onSkin={flipSkin} selected={selected} onPick={pick} objects={view.props.filter((p) => p.kind !== 'item').map((p) => ({ id: p.id, name: p.kind.replace(/_/g, ' ') }))} onTarget={act} onImprovise={improvise} onCancel={() => setPicked(null)} />}
    </div>
  )
}
