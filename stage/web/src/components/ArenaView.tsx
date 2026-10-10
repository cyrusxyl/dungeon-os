import { useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/8bit/button'
import { Hand } from '@/components/Hand'
import type { Ability, ArenaUnit, ArenaView as View, Cell, Preview } from '@/lib/arena'
import { useHand, useSkin } from '@/lib/hand'
import { BAND_FILL } from '@/lib/party'
import { deviceHeaders, postJson, type StageState, useIntegerScale, useJson } from '@/lib/stage'
import { T, useImages, variant } from '@/lib/tiles'

type Image = (url: string) => HTMLImageElement | undefined

function drawTiles(ctx: CanvasRenderingContext2D, view: View, image: Image) {
  const atlas = image(`/asset/arena/${view.id}.png`)
  const hazard = image(`/asset/icon/${view.hazard}.png`)
  const tile = (col: number, row: number, px: number, py: number) => atlas && ctx.drawImage(atlas, col * T, row * T, T, T, px, py, T, T)
  for (let y = 0; y < view.h; y++) {
    for (let x = 0; x < view.w; x++) {
      const c = view.grid[y][x]
      const px = x * T
      const py = y * T
      if (c === ' ') continue // never seen (fog): stays black
      if (c === '#') {
        tile(variant(x, y, view.tiles.walls), 0, px, py)
        continue
      }
      tile(view.tiles.pattern ? (x % 2) + (y % 2) * 2 : variant(x, y, view.tiles.floors), 1, px, py)
      if (c === 'd') tile(1, 2, px, py)
      if (c === '~' && hazard) ctx.drawImage(hazard, 0, 0, T, T, px, py, T, T)
    }
  }
}

/** A picture stands on its cell, centered, feet at the bottom edge; a tall one overlaps the cell above. */
function stand(ctx: CanvasRenderingContext2D, img: HTMLImageElement, x: number, y: number, alpha = 1) {
  ctx.globalAlpha = alpha
  ctx.drawImage(img, x * T + (T - img.width) / 2, (y + 1) * T - img.height)
  ctx.globalAlpha = 1
}

function drawUnit(ctx: CanvasRenderingContext2D, u: ArenaUnit, image: Image, current: boolean) {
  const img = image(`/asset/actor/${encodeURIComponent(u.id)}/full.png`)
  const alpha = u.down ? 0.35 : 1
  if (img) {
    stand(ctx, img, u.x, u.y, alpha)
  } else {
    ctx.globalAlpha = alpha
    ctx.fillStyle = u.pc ? '#5fa8e0' : '#e5534f'
    ctx.fillRect(u.x * T + 6, u.y * T + 6, T - 12, T - 12)
    ctx.fillStyle = '#000'
    ctx.font = 'bold 14px sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText(u.name.charAt(0), u.x * T + T / 2, u.y * T + T / 2 + 5)
    ctx.globalAlpha = 1
  }
  if (current) {
    ctx.strokeStyle = '#c9a96e'
    ctx.lineWidth = 2
    ctx.strokeRect(u.x * T + 1, u.y * T + 1, T - 2, T - 2)
  }
  if (u.intent && !u.down) drawIntent(ctx, u)
  const fill = u.hp ? (u.hp.current / (u.hp.max || 1)) * 100 : BAND_FILL[u.health]
  ctx.fillStyle = '#000'
  ctx.fillRect(u.x * T + 3, u.y * T + T - 5, T - 6, 4)
  ctx.fillStyle = u.pc ? '#6fcf6f' : '#e05050'
  ctx.fillRect(u.x * T + 4, u.y * T + T - 4, Math.round(((T - 8) * fill) / 100), 2)
}

/** A small label over a creature: what it will do on its turn. */
function drawIntent(ctx: CanvasRenderingContext2D, u: ArenaUnit) {
  const text = u.intent!.text
  ctx.font = '8px sans-serif'
  ctx.textAlign = 'center'
  const w = Math.min(ctx.measureText(text).width + 6, T * 3)
  const x = u.x * T + T / 2
  const y = u.y * T - 2
  ctx.fillStyle = u.intent!.kind === 'dm' ? 'rgba(20,50,90,0.85)' : 'rgba(60,10,10,0.85)'
  ctx.fillRect(x - w / 2, y - 10, w, 10)
  ctx.fillStyle = u.intent!.kind === 'move' ? '#c9a96e' : '#ffd6d3'
  ctx.fillText(text, x, y - 2, T * 3 - 6)
}

function draw(ctx: CanvasRenderingContext2D, view: View, hover: [number, number] | null, canWalk: boolean, image: Image, aim: Preview | null) {
  ctx.imageSmoothingEnabled = false
  ctx.fillStyle = '#000'
  ctx.fillRect(0, 0, view.w * T, view.h * T)
  drawTiles(ctx, view, image)
  if (canWalk && !aim) {
    ctx.fillStyle = 'rgba(95, 168, 224, 0.28)'
    for (const [x, y] of view.walk) ctx.fillRect(x * T, y * T, T, T)
  }
  if (aim) {
    ctx.fillStyle = aim.ok ? 'rgba(224, 90, 60, 0.38)' : 'rgba(120, 120, 120, 0.3)'
    for (const [x, y] of aim.cells) ctx.fillRect(x * T, y * T, T, T)
  }
  if (hover) {
    ctx.strokeStyle = '#fff'
    ctx.lineWidth = 1
    ctx.strokeRect(hover[0] * T + 0.5, hover[1] * T + 0.5, T - 1, T - 1)
  }
  for (const item of view.items) {
    ctx.fillStyle = '#7fb2d6'
    ctx.beginPath()
    ctx.arc(item.x * T + T / 2, item.y * T + T / 2, 5, 0, Math.PI * 2)
    ctx.fill()
  }
  // Props and creatures in depth order: one lower on the screen stands in front.
  const things = [
    ...view.props.map((p) => ({ y: p.y, prop: p, unit: undefined })),
    ...view.units.map((u) => ({ y: u.y + 0.5, prop: undefined, unit: u })),
  ].sort((a, b) => a.y - b.y)
  for (const t of things) {
    if (t.unit) {
      drawUnit(ctx, t.unit, image, t.unit.id === view.current)
    } else if (t.prop) {
      const img = image(`/asset/prop/${t.prop.kind}.png`)
      if (img) stand(ctx, img, t.prop.x, t.prop.y)
    }
  }
  if (aim) {
    ctx.strokeStyle = '#ffd24a'
    ctx.lineWidth = 2
    for (const u of view.units) if (aim.units.includes(u.id)) ctx.strokeRect(u.x * T + 2, u.y * T + 2, T - 4, T - 4)
  }
  if (view.visible) {
    // The shade over what the party has seen but cannot see now.
    ctx.fillStyle = 'rgba(8, 6, 14, 0.62)'
    for (let y = 0; y < view.h; y++) {
      for (let x = 0; x < view.w; x++) if (view.grid[y][x] !== ' ' && view.visible[y][x] === '0') ctx.fillRect(x * T, y * T, T, T)
    }
  }
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
  // Half steps (1, 1.5, 2...): a small board fills the frame, and each source pixel is still drawn whole or half.
  const scale = Math.max(1, useIntegerScale(box, ((view?.w ?? 16) * T) / 2, ((view?.h ?? 10) * T) / 2) / 2)
  const [image, tick] = useImages()
  const [hover, setHover] = useState<[number, number] | null>(null)
  const [note, setNote] = useState('')
  const busy = useRef(false)
  const canWalk = Boolean(view && actingAs && view.current === actingAs && !view.pending)
  const version = state.versions?.[`arena:${arenaId}`] ?? 0
  const hand = useHand(canWalk ? actingAs : null, version)
  const [skin, flipSkin] = useSkin()
  const [picked, setPicked] = useState<string | null>(null)
  const [aim, setAim] = useState<Preview | null>(null)
  // The ability is read from the fresh hand, so its targets and reasons never go stale.
  const selected: Ability | null = hand?.abilities.find((ab) => ab.id === picked && !ab.why) ?? null
  const aimed = selected?.needs === 'aim' ? selected : null
  const aimedId = aimed?.id ?? null

  useEffect(() => {
    const ctx = canvas.current?.getContext('2d')
    if (ctx && view) draw(ctx, view, hover, canWalk, image, aimed ? aim : null)
  }, [view, hover, canWalk, image, tick, aim, aimed])
  useEffect(() => {
    if (!aimedId || !hover || !actingAs) return
    let live = true
    fetch('/api/arena/preview', { method: 'POST', headers: { 'Content-Type': 'application/json', ...deviceHeaders() }, body: JSON.stringify({ who: actingAs, ability: aimedId, aim: hover }) })
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null)
      .then((p: Preview | null) => live && setAim(p))
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

  const cellAt = (e: React.MouseEvent<HTMLCanvasElement>): [number, number] => {
    const rect = e.currentTarget.getBoundingClientRect()
    return [Math.floor(((e.clientX - rect.left) / rect.width) * view.w), Math.floor(((e.clientY - rect.top) / rect.height) * view.h)]
  }
  const call = async (path: string, body: Record<string, unknown>) => {
    if (busy.current) return
    busy.current = true
    try {
      const res = await postJson(path, body)
      if (!res.ok) setNote(((await res.json().catch(() => null)) as { error?: string } | null)?.error ?? 'The board refused that.')
    } finally {
      busy.current = false
    }
  }
  const act = async (ab: Ability, target?: string, at?: Cell) => {
    if (!actingAs) return
    await call('/api/arena/act', { who: actingAs, ability: ab.id, target, aim: at })
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
    const [x, y] = cellAt(e)
    if (aimed) return act(aimed, undefined, [x, y])
    const foe = view.units.find((u) => !u.pc && !u.down && u.x === x && u.y === y)
    if (foe && selected?.needs === 'target') act(selected, foe.id)
    else if (foe) call('/api/arena/attack', { who: actingAs, target: foe.id })
    else if (view.walk.some(([wx, wy]) => wx === x && wy === y)) call('/api/arena/move', { who: actingAs, to: [x, y] })
    else setNote('You cannot walk there this turn.')
  }
  const asked = view.pending && mine.includes(view.pending.who) ? view.pending : null
  const name = (id: string) => view.units.find((u) => u.id === id)?.name ?? id

  return (
    <div className="flex h-full w-full flex-col">
      <div ref={box} className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden">
        <canvas
          ref={canvas}
          width={view.w * T}
          height={view.h * T}
          onClick={click}
          onMouseMove={(e) => {
            const [x, y] = cellAt(e)
            setHover((prev) => (prev && prev[0] === x && prev[1] === y ? prev : [x, y])) // one redraw per cell crossed
          }}
          onMouseLeave={() => setHover(null)}
          aria-label="The board of the fight. Click a blue cell to walk. Click a creature to attack it."
          className={`pixelated shrink-0 ${canWalk ? 'cursor-pointer' : 'cursor-default'}`}
          style={{ width: view.w * T * scale, height: view.h * T * scale }}
        />
        <div className="pointer-events-none absolute top-2 left-2 flex flex-col gap-1">
          <span className="pixel-font bg-black/60 px-2 py-1 text-[10px] text-[var(--gold)]">
            Round {view.round}
            {canWalk ? ` · ${view.feet_left} ft left` : ''}
          </span>
          {note && <span className="pixel-font bg-black/70 px-2 py-1 text-[8px] text-[var(--bad)]">{note}</span>}
        </div>
        {isHost && <CombatSettings settings={state.combat_settings ?? view.settings} />}
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
    {hand && canWalk && <Hand hand={hand} skin={skin} onSkin={flipSkin} selected={selected} onPick={pick} objects={view.props.filter((p) => p.kind !== 'item').map((p) => ({ id: p.id, name: p.kind.replace(/_/g, ' ') }))} onTarget={act} onImprovise={improvise} onCancel={() => setPicked(null)} />}
    </div>
  )
}
