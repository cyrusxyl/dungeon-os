import { useEffect, useMemo, useState } from 'react'

import { SceneCanvas, type SceneActor } from '@/components/SceneCanvas'
import { geometry, groundCentre, roomCentre } from '@/lib/iso'
import { usePropsInfo } from '@/lib/propAtlas'
import { faceOf } from '@/lib/props'
import { decorCentre, pointOn, type SceneRoom } from '@/lib/scene'
import { useJson } from '@/lib/stage'

const FLAVOUR = ['Shuffling the notes', 'Sharpening quills', 'Consulting the dice', 'Warming up the voices']
const SHOWN = 2
// The DM paces the floor in front of the desk: the cells of its walk, there and back.
const PACE: [number, number][] = [[2, 5], [3, 5], [4, 5], [5, 5], [6, 5], [7, 5], [6, 5], [5, 5], [4, 5], [3, 5]]

function useTick(ms: number): number {
  const [i, setI] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setI((n) => n + 1), ms)
    return () => clearInterval(t)
  }, [ms])
  return i
}

// The DM at work in its study: shown in place of the stage while there is no scene yet.
export function DmTable({ activity }: { activity?: string[] }) {
  const list = activity ?? []
  const room = useJson<SceneRoom>('/api/filler')
  const props = usePropsInfo()
  const step = useTick(2200)
  const cell = PACE[step % PACE.length]
  const was = PACE[(step + PACE.length - 1) % PACE.length]
  const facing = cell[0] >= was[0] ? 'right' : 'left'
  const cast = useMemo<SceneActor[]>(
    () => [{ id: 'wizard', side: 'neutral', cell, facing, sit: false, onProp: false, bare: true, src: `/asset/actor/wizard/full.png?d=${facing}` }],
    [cell, facing],
  )
  const current = list.at(-1) ?? FLAVOUR[Math.floor(step / 1.2) % FLAVOUR.length]
  const done = list.slice(-SHOWN - 1, -1)

  // The light of the fire and of the lamp on the desk, as a place in percent of the picture.
  const g = room && geometry(room.w, room.h)
  const at = (p: [number, number]): React.CSSProperties => (g ? { left: `${(p[0] / g.width) * 100}%`, top: `${(p[1] / g.height) * 100}%` } : {})
  const fire = g && room.decor.find((d) => d.kind === 'fireplace' || d.kind === 'hearth')
  const lampStuff = g && room.stuff.find((s) => s.icon.includes('lamp'))
  const desk = g && lampStuff && room.props.find((p) => p.kind === lampStuff.on)
  const lampEntry = lampStuff && props?.props[lampStuff.on]
  let lamp: [number, number] | undefined
  if (g && desk && lampEntry && lampStuff) {
    const [cx, cy] = groundCentre(g, desk.x, desk.y)
    const [dx, dy] = pointOn(lampEntry, faceOf(desk.x, desk.y, roomCentre(room.grid)), lampStuff.at[0], lampStuff.at[1])
    lamp = [cx + dx, cy + dy - 14]
  }

  return (
    <div className="absolute inset-0 overflow-hidden" role="status" aria-live="polite">
      {room?.has_look && (
        <SceneCanvas room={room} sheetUrl="/asset/filler/room.png?v=3" cast={cast} mood={room.mood}>
          {/* Light only: the objects are in the room picture. */}
          {fire && <div className="dm-glow absolute h-[12%] w-[12%] -translate-x-1/2 -translate-y-1/2" style={at(decorCentre(g, fire, 40))} />}
          {lamp && <div className="dm-glow absolute h-[10%] w-[8%] -translate-x-1/2 -translate-y-1/2" style={{ ...at(lamp), animationDelay: '0.3s' }} />}
        </SceneCanvas>
      )}
      <div className="pixel-font absolute inset-x-0 bottom-0 flex flex-col justify-end gap-1 border-t-2 border-[var(--border)] bg-[var(--panel)]/90 px-3 py-2">
        {done.map((label, i) => (
          <div key={`${label}-${i}`} className="truncate text-[10px] text-[var(--dim)] opacity-70">
            <span className="text-emerald-400">✓ </span>
            {label}
          </div>
        ))}
        <div className="truncate text-xs text-[var(--gold)]">
          {current}
          <span className="dm-dots" />
        </div>
      </div>
    </div>
  )
}
