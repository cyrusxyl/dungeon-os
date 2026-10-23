import { useEffect, useMemo, useRef } from 'react'

import { byDepth, geometry, groundCentre, roomCentre, S, unitDepth, type Base, type Geometry, type Pt as Point } from '@/lib/iso'
import type { Placed } from '@/lib/layout'
import { usePropsInfo, type PropsInfo } from '@/lib/propAtlas'
import { faceOf } from '@/lib/props'
import { decorCentre, pointOn, type SceneRoom } from '@/lib/scene'
import { propThing, sceneBase, sceneStyle, type Thing } from '@/lib/roomDraw'
import { type Side, useFitScale } from '@/lib/stage'
import { useImages, type ImageLoader } from '@/lib/tiles'

/** The scene's mood as a filter on the whole picture: floor, walls, props and actors alike. */
const MOOD_FILTER: Record<string, string> = {
  day: 'none',
  dusk: 'sepia(0.2) brightness(0.92)',
  night: 'brightness(0.6) saturate(0.7) hue-rotate(10deg)',
  torchlit: 'brightness(0.8) sepia(0.25)',
  fog: 'contrast(0.85) brightness(1.05) saturate(0.8)',
  rain: 'brightness(0.75) saturate(0.8)',
  snow: 'brightness(1.03) saturate(0.85)',
}

const RING: Record<Side, string> = { party: '#5fd08a', ally: '#5fd08a', neutral: '#e8c14a', bystander: '#e8c14a', hostile: '#ef6a5a' }
const HIP_ROW = 48 // a seated frame puts its hip row on the seat
const MOVE_MS = 300

/** What a click on the picture hit: a figure, or an exit (a door in the wall). */
export type Pick = { kind: 'actor'; id: string } | { kind: 'exit'; name: string }
const EXIT = /door|gate|arch|stair/
const HIT = 24 // how close a click must be to a figure or a door, in logical px

export interface SceneActor extends Placed {
  /** The picture of the actor: `/asset/actor/<id>/full.png?...`. */
  src: string
  /** No ring under the feet (the DM at work in its study). */
  bare?: boolean
}

type Pos = [number, number]

/** Where an actor's feet (or, seated, its hip) are, in logical px. */
function anchor(g: Geometry, props: PropsInfo | undefined, p: Placed, centre: Point): Pos {
  const [cx, cy] = groundCentre(g, p.cell[0], p.cell[1])
  const entry = p.spot && props?.props[p.spot.stand.prop]
  if (!p.spot || !entry) return [cx, cy]
  const [dx, dy] = pointOn(entry, faceOf(p.cell[0], p.cell[1], centre), p.spot.point[0], p.spot.point[1])
  return [cx + dx, cy + dy]
}

function drawActor(ctx: CanvasRenderingContext2D, p: SceneActor, at: Pos, speaker: boolean, image: ImageLoader) {
  const [ax, ay0] = at
  const ay = ay0 - (speaker ? 2 : 0)
  ctx.setTransform(S, 0, 0, S, 0, 0)
  if (!p.sit && !p.bare && !p.down) {
    ctx.fillStyle = RING[p.side]
    ctx.globalAlpha = 0.75
    ctx.strokeStyle = '#0008'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.ellipse(ax, ay, 15, 6, 0, 0, Math.PI * 2)
    ctx.fill()
    ctx.stroke()
    ctx.globalAlpha = 1
  }
  const img = image(p.src)
  if (img && p.down) {
    // A fallen figure lies on its side on the floor: the sprite turned a quarter, its feet on the spot.
    ctx.save()
    ctx.translate(ax, ay)
    ctx.rotate(-Math.PI / 2)
    ctx.globalAlpha = 0.85
    ctx.drawImage(img, Math.round(-img.width / 2), Math.round(-(img.height - 4) / 2) - 2)
    ctx.restore()
  } else if (img) {
    ctx.drawImage(img, Math.round(ax - img.width / 2), Math.round(p.sit ? ay - HIP_ROW : ay - (img.height - 4)))
  } else {
    // Until the picture arrives: a plain figure, never a guess.
    ctx.fillStyle = '#3a3350'
    ctx.beginPath()
    ctx.ellipse(ax, ay - 38, 8, 8, 0, 0, Math.PI * 2)
    ctx.fill()
    ctx.fillRect(ax - 10, ay - 30, 20, 26)
  }
}

interface Props {
  room: SceneRoom
  /** The room's sheet: `/asset/scene/<location>/room.png`. */
  sheetUrl: string
  cast?: SceneActor[]
  speaker?: string
  mood?: string
  /** A click on the picture: what it hit (null: nothing) and where, in percent of the picture. Off when not given. */
  onPick?: (hit: Pick | null, at: { left: number; top: number }) => void
  /** Fill the box and crop (a backdrop) instead of fitting inside it. */
  cover?: boolean
  className?: string
  /** Laid over the picture in its own coordinates: left and top in percent of the picture. */
  children?: React.ReactNode
}

/**
 * A scene room, drawn on the renderer of the combat board: the floor and the walls with their decor once, then the props
 * and the actors back to front. An actor walks to a new place in a short tween.
 */
export function SceneCanvas({ room, sheetUrl, cast = [], speaker, mood = 'day', onPick, cover = false, className = '', children }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const g = useMemo(() => geometry(room.w, room.h), [room.w, room.h])
  const centre = useMemo(() => roomCentre(room.grid), [room.grid])
  const scale = useFitScale(box, g.width, g.height)
  const [image, tick] = useImages()
  const props = usePropsInfo()
  const atlas = props ? image(props.atlas) : undefined
  const sheet = image(sheetUrl)
  const base = useRef<{ key: unknown[]; base: Base } | null>(null)
  const shown = useRef(new Map<string, Pos>())

  useEffect(() => {
    const ctx = canvas.current?.getContext('2d')
    if (!ctx) return
    const key = [room, sheet, props, atlas]
    if (!base.current || base.current.key.some((k, i) => k !== key[i])) base.current = { key, base: sceneBase(room, room.grid, g, sceneStyle(room, sheet), props, atlas) }
    const { rims } = base.current.base
    const to = new Map(cast.map((p) => [p.id, anchor(g, props, p, centre)] as const))
    const from = new Map(cast.map((p) => [p.id, shown.current.get(p.id) ?? to.get(p.id)!] as const))
    const still = matchMedia('(prefers-reduced-motion: reduce)').matches
    const start = performance.now()
    let raf = 0

    const frame = (now: number) => {
      const f = still ? 1 : Math.min(1, (now - start) / MOVE_MS)
      const ease = 1 - (1 - f) ** 3
      shown.current = new Map(cast.map((p) => {
        const [x0, y0] = from.get(p.id)!
        const [x1, y1] = to.get(p.id)!
        return [p.id, [x0 + (x1 - x0) * ease, y0 + (y1 - y0) * ease]] as const
      }))
      ctx.imageSmoothingEnabled = false
      ctx.setTransform(1, 0, 0, 1, 0, 0)
      ctx.drawImage(base.current!.base.canvas, 0, 0)
      const things: Thing[] = rims.map((r) => ({ depth: r.depth, draw: () => r.draw(ctx) }))
      if (props && atlas) {
        for (const p of room.props) {
          const thing = propThing(ctx, g, props, atlas, p, centre)
          if (thing) things.push(thing)
        }
        // The clutter on a desk: an icon set on a point of the desk's picture.
        for (const s of room.stuff) {
          const desk = room.props.find((p) => p.kind === s.on)
          const entry = props.props[s.on]
          if (!desk || !entry || !sheet) continue
          things.push({
            depth: unitDepth(desk.x, desk.y) + 0.003,
            draw: () => {
              const [cx, cy] = groundCentre(g, desk.x, desk.y)
              const [dx, dy] = pointOn(entry, faceOf(desk.x, desk.y, centre), s.at[0], s.at[1])
              const [sx, sy, w, h] = s.r
              ctx.setTransform(S, 0, 0, S, 0, 0)
              ctx.drawImage(sheet, sx, sy, w, h, Math.round(cx + dx - w / 2), Math.round(cy + dy - h), w, h)
            },
          })
        }
      }
      for (const p of cast) {
        const at = shown.current.get(p.id)!
        const bump = p.onProp ? 0.005 : 0
        things.push({ depth: unitDepth(p.cell[0], p.cell[1]) + bump, draw: () => drawActor(ctx, p, at, p.id === speaker, image) })
      }
      for (const t of byDepth(things)) t.draw()
      if (f < 1) raf = requestAnimationFrame(frame)
    }
    raf = requestAnimationFrame(frame)
    return () => cancelAnimationFrame(raf)
  }, [room, cast, speaker, tick, props, atlas, sheet, image, g, centre]) // eslint-disable-line react-hooks/exhaustive-deps

  const filter = MOOD_FILTER[mood] ?? 'none'
  // The cast and the geometry as data on the canvas: the picture has no text, and the tests read it from here (the geometry: ox, oy, width, height).
  const shot = useMemo(() => JSON.stringify(cast.map((p) => ({ id: p.id, side: p.side, cell: p.cell, sit: p.sit, onProp: p.onProp, down: Boolean(p.down) }))), [cast])
  const picture = (
    <canvas
      ref={canvas}
      width={g.width * S}
      height={g.height * S}
      data-cast={shot}
      data-geom={`${g.ox},${g.oy},${g.width},${g.height}`}
      aria-hidden="true"
      onClick={
        onPick && !cover
          ? (e) => {
              const rect = e.currentTarget.getBoundingClientRect()
              const [x, y] = [((e.clientX - rect.left) / rect.width) * g.width, ((e.clientY - rect.top) / rect.height) * g.height]
              const near = (px: number, py: number) => Math.hypot(px - x, py - y)
              let hit: Pick | null = null
              let best = HIT
              for (const p of cast) {
                const at = shown.current.get(p.id)
                if (!at || p.down || near(at[0], at[1] - 30) >= best) continue
                best = near(at[0], at[1] - 30)
                hit = { kind: 'actor', id: p.id }
              }
              if (!hit) {
                for (const d of room.decor) {
                  const [dx, dy] = decorCentre(g, d)
                  if (EXIT.test(d.kind) && near(dx, dy) < best) {
                    best = near(dx, dy)
                    hit = { kind: 'exit', name: d.kind.replace(/_/g, ' ') }
                  }
                }
              }
              onPick(hit, { left: (x / g.width) * 100, top: (y / g.height) * 100 })
            }
          : undefined
      }
      className={`pixelated ${onPick && !cover ? 'cursor-pointer ' : ''}${cover ? 'absolute inset-0 h-full w-full object-cover' : 'block'} ${className}`}
      style={{ filter, ...(cover ? {} : { width: g.width * scale, height: g.height * scale }) }}
    />
  )
  if (cover) return <div ref={box} className="absolute inset-0 overflow-hidden">{picture}</div>
  return (
    <div ref={box} className="relative flex h-full w-full items-center justify-center overflow-hidden">
      <div className="relative shrink-0" style={{ width: g.width * scale, height: g.height * scale }}>
        {picture}
        {children}
      </div>
    </div>
  )
}
