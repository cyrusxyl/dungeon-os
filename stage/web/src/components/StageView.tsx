import { useMemo } from 'react'

import { DmTable } from '@/components/DmTable'
import { SceneCanvas, type SceneActor } from '@/components/SceneCanvas'
import { layout } from '@/lib/layout'
import { blankRoom, type SceneRoom } from '@/lib/scene'
import { postJson, type StageState, useJson } from '@/lib/stage'

/** The scene room as the browser draws it: the room of the scene when it has a look, else bare floor. */
const NO_LOOK: SceneRoom = { ...blankRoom(), props: [], has_look: false, mood: 'day', open: true, shaped: false, decor: [], stand: [], stuff: [], sheet: { w: 0, h: 0, north: [0, 0], west: [0, 0], stuff: 0 } }

/** `walkAs`: the character this device plays; a click on the floor sends it there (the server checks the seat and the way). */
export function StageView({ state, speaker, walkAs }: { state: StageState; speaker?: string; walkAs?: string | null }) {
  const scene = state.scene
  const version = state.versions?.[`scene:${scene}`] ?? 0
  const data = useJson<SceneRoom>(scene ? `/api/scene/${encodeURIComponent(scene)}?v=${version}` : null, version)
  const room = data?.has_look ? data : NO_LOOK
  const actors = state.actors
  const versions = state.versions
  const cast = useMemo<SceneActor[]>(
    () =>
      layout(actors, room.stand, room).map((p) => ({
        ...p,
        src: `/asset/actor/${encodeURIComponent(p.id)}/full.png?d=${p.facing}${p.sit ? '&pose=sit' : ''}&v=${versions?.[p.id] ?? 0}`,
      })),
    [actors, room, versions],
  )

  if (!scene && Object.keys(actors).length === 0) {
    return state.dm.status === 'starting' || state.dm.status === 'busy' ? (
      <DmTable activity={state.activity} />
    ) : (
      <div className="absolute inset-0 grid place-items-center text-[8px] text-[var(--dim)] pixel-font">No scene yet</div>
    )
  }
  return (
    <SceneCanvas
      key={scene ?? ''}
      room={room}
      sheetUrl={data?.has_look ? `/asset/scene/${encodeURIComponent(scene!)}/room.png?v=${version}` : ''}
      cast={cast}
      speaker={speaker}
      mood={room.mood}
      onCell={walkAs && state.actors[walkAs] ? (to) => void postJson('/api/scene/walk', { who: walkAs, to }) : undefined}
      className="scene-in"
    />
  )
}
