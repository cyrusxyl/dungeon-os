import { useCallback, useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/8bit/button'
import { focusTakesText, postJson, type StageState, useIntegerScale, useJson } from '@/lib/stage'
import { T, useImages, variant } from '@/lib/tiles'

// A window of 15 x 9 tiles of 32 px that follows the party.
const VIEW_W = 15
const VIEW_H = 9
const W = VIEW_W * T
const H = VIEW_H * T
const STEP_MS = 70

type Cell = [number, number]
type Facing = 'up' | 'down' | 'left' | 'right'

export interface SiteView {
  id: string
  name: string
  theme: string
  w: number
  h: number
  cells: string[]
  visible: string[]
  party: Cell
  entrance: Cell
  pois: { id: string; name: string; x: number; y: number; url: string }[]
  tiles: { walls: number; floors: number; pattern: boolean }
  lead: string | null
}

const KEYS: Record<string, Facing> = {
  ArrowUp: 'up', w: 'up', W: 'up',
  ArrowDown: 'down', s: 'down', S: 'down',
  ArrowLeft: 'left', a: 'left', A: 'left',
  ArrowRight: 'right', d: 'right', D: 'right',
}

function camera(size: number, view: number, at: number): number {
  if (size <= view) return -Math.floor((view - size) / 2)
  return Math.min(Math.max(at - Math.floor(view / 2), 0), size - view)
}

function facingOf(from: Cell, to: Cell): Facing {
  if (to[0] > from[0]) return 'right'
  if (to[0] < from[0]) return 'left'
  return to[1] < from[1] ? 'up' : 'down'
}

function draw(ctx: CanvasRenderingContext2D, view: SiteView, pos: Cell, facing: Facing, image: (url: string) => HTMLImageElement | undefined) {
  ctx.imageSmoothingEnabled = false
  ctx.fillStyle = '#000'
  ctx.fillRect(0, 0, W, H)
  const atlas = image(`/asset/crawl/${view.theme}.png`)
  const cx = camera(view.w, VIEW_W, pos[0])
  const cy = camera(view.h, VIEW_H, pos[1])
  const tile = (col: number, row: number, px: number, py: number) => atlas && ctx.drawImage(atlas, col * T, row * T, T, T, px, py, T, T)
  const lit = (x: number, y: number) => view.visible[y]?.[x] === '1'
  ctx.fillStyle = 'rgba(8, 6, 14, 0.62)' // the shade over cells seen before but not in sight now

  for (let vy = 0; vy < VIEW_H; vy++) {
    for (let vx = 0; vx < VIEW_W; vx++) {
      const x = cx + vx
      const y = cy + vy
      const c = view.cells[y]?.[x] ?? ' '
      if (c === ' ') continue
      const px = vx * T
      const py = vy * T
      if (c === '#') {
        tile(variant(x, y, view.tiles.walls), 0, px, py)
      } else {
        const f = view.tiles.pattern ? (x % 2) + (y % 2) * 2 : variant(x, y, view.tiles.floors)
        tile(f, 1, px, py)
        const special = { '+': 0, "'": 1, '<': 2 }[c]
        if (special !== undefined) tile(special, 2, px, py)
      }
      if (!lit(x, y)) ctx.fillRect(px, py, T, T)
    }
  }

  // Sprites stand on their cell: a 64 px LPC frame overlaps the cell above.
  const sprite = (img: HTMLImageElement, x: number, y: number) => {
    const px = (x - cx) * T
    const py = (y - cy) * T
    if (img.width > T) ctx.drawImage(img, px - (img.width - T) / 2, py + T - img.height)
    else ctx.drawImage(img, px, py)
  }
  // Sprites in depth order: one lower on the screen stands in front.
  const lead = view.lead ? image(`/asset/actor/${encodeURIComponent(view.lead)}/full.png?d=${facing}`) : undefined
  const sprites = view.pois.flatMap((p) => {
    const img = image(p.url)
    return img ? [{ img, x: p.x, y: p.y, dim: !lit(p.x, p.y) }] : []
  })
  if (lead) sprites.push({ img: lead, x: pos[0], y: pos[1], dim: false })
  for (const t of sprites.sort((a, b) => a.y - b.y)) {
    ctx.globalAlpha = t.dim ? 0.5 : 1
    sprite(t.img, t.x, t.y)
  }
  ctx.globalAlpha = 1
  if (!lead) {
    ctx.fillStyle = '#55ff33'
    ctx.fillRect((pos[0] - cx) * T + 8, (pos[1] - cy) * T + 8, 16, 16)
  }

  // Torchlight: dark at the edge of sight.
  const ox = (pos[0] - cx) * T + T / 2
  const oy = (pos[1] - cy) * T + T / 2
  const light = ctx.createRadialGradient(ox, oy, T * 2.5, ox, oy, T * 9)
  light.addColorStop(0, 'rgba(0,0,0,0)')
  light.addColorStop(1, 'rgba(0,0,0,0.5)')
  ctx.fillStyle = light
  ctx.fillRect(0, 0, W, H)
}

/**
 * The party walks a site: keys or a click move it; the server does sight and
 * the checks that call the DM. Walking needs no DM turn.
 */
export function CrawlView({ state, siteId, canAct }: { state: StageState; siteId: string; canAct: boolean }) {
  const box = useRef<HTMLDivElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const scale = useIntegerScale(box, W, H)
  const fetched = useJson<SiteView>(`/api/site/${encodeURIComponent(siteId)}`, state.versions?.[`site:${siteId}`] ?? 0)
  // A walk's answer, until the next fetch replaces it.
  const [walked, setWalked] = useState<SiteView | null>(null)
  const view = walked ?? fetched
  const viewRef = useRef(view)
  viewRef.current = view
  const [pos, setPos] = useState<Cell | null>(null)
  const [facing, setFacing] = useState<Facing>('down')
  const [image, tick] = useImages()
  const walking = useRef(false)
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => {
    setWalked(null)
    if (fetched) setPos(fetched.party)
  }, [fetched])

  useEffect(() => {
    const ctx = canvas.current?.getContext('2d')
    if (ctx && view && pos) draw(ctx, view, pos, facing, image)
  }, [view, pos, facing, image, tick])

  useEffect(() => () => window.clearTimeout(timer.current), [])

  const go = useCallback(
    async (body: { dir: Facing } | { to: Cell }) => {
      const view = viewRef.current
      if (!canAct || walking.current || !view) return
      walking.current = true
      if ('dir' in body) setFacing(body.dir)
      try {
        const res = await postJson(`/api/site/${encodeURIComponent(siteId)}/move`, body)
        if (!res.ok) return
        const next: SiteView & { path: Cell[] } = await res.json()
        // Walk the marker along the path, then show the end state.
        let prev = view.party
        for (const step of next.path) {
          const from = prev
          await new Promise<void>((done) => {
            timer.current = window.setTimeout(done, next.path.length > 1 ? STEP_MS : 0)
          })
          setFacing(facingOf(from, step))
          setPos(step)
          prev = step
        }
        setWalked(next)
        setPos(next.party)
      } finally {
        walking.current = false
      }
    },
    [canAct, siteId],
  )

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const dir = KEYS[e.key]
      // A focused button (the dialogue box, Examine) has no use for arrows or letters.
      if (!dir || focusTakesText(e) || e.ctrlKey || e.metaKey || e.altKey) return
      e.preventDefault()
      go({ dir })
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [go])

  if (view === undefined) return <div ref={box} className="h-full w-full" />
  if (view === null) {
    return (
      <div ref={box} className="pixel-font grid h-full w-full place-items-center text-[8px] text-[var(--dim)]">
        The DM is still drawing this place…
      </div>
    )
  }

  const click = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!pos) return
    const rect = e.currentTarget.getBoundingClientRect()
    const x = Math.floor(((e.clientX - rect.left) / rect.width) * VIEW_W) + camera(view.w, VIEW_W, pos[0])
    const y = Math.floor(((e.clientY - rect.top) / rect.height) * VIEW_H) + camera(view.h, VIEW_H, pos[1])
    if (view.cells[y]?.[x] && view.cells[y][x] !== ' ' && view.cells[y][x] !== '#') go({ to: [x, y] })
  }

  const [px, py] = view.party
  const near = view.pois.filter((p) => Math.max(Math.abs(p.x - px), Math.abs(p.y - py)) <= 1)
  const onExit = px === view.entrance[0] && py === view.entrance[1]
  const act = (body: { kind: 'examine'; poi: string } | { kind: 'leave' }) =>
    canAct && postJson(`/api/site/${encodeURIComponent(siteId)}/act`, body)

  return (
    <div ref={box} className="relative flex h-full w-full items-center justify-center overflow-hidden">
      <canvas
        ref={canvas}
        width={W}
        height={H}
        onClick={click}
        aria-label={`Map of ${view.name || 'the site'}. Arrow keys or WASD walk; click a seen spot to go there.`}
        className={`pixelated shrink-0 ${canAct ? 'cursor-pointer' : 'cursor-wait'}`}
        style={{ width: W * scale, height: H * scale }}
      />
      <div className="pointer-events-none absolute top-2 left-2 flex flex-col gap-1">
        <span className="pixel-font bg-black/60 px-2 py-1 text-[10px] text-[var(--gold)]">{view.name}</span>
        {!canAct && <span className="pixel-font bg-black/60 px-2 py-1 text-[8px] text-[var(--dim)]">The story goes on…</span>}
      </div>
      {(near.length > 0 || onExit) && (
        <div className="absolute right-2 bottom-2 flex flex-wrap justify-end gap-2">
          {near.map((p) => (
            <Button key={p.id} size="sm" disabled={!canAct} onClick={() => act({ kind: 'examine', poi: p.id })} className="text-[10px]">
              Examine {p.name}
            </Button>
          ))}
          {onExit && (
            <Button size="sm" variant="outline" disabled={!canAct} onClick={() => act({ kind: 'leave' })} className="text-[10px]">
              Leave {view.name}
            </Button>
          )}
        </div>
      )}
    </div>
  )
}
