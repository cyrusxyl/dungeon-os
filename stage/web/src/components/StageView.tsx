import { useMemo, useState } from 'react'

import { DmTable } from '@/components/DmTable'
import { SceneCanvas, type Pick, type SceneActor } from '@/components/SceneCanvas'
import { layout } from '@/lib/layout'
import { blankRoom, type SceneRoom } from '@/lib/scene'
import { titleCase, type StageState, useJson } from '@/lib/stage'

/** The scene room as the browser draws it: the room of the scene when it has a look, else bare floor. */
const NO_LOOK: SceneRoom = { ...blankRoom(), props: [], has_look: false, mood: 'day', open: true, shaped: false, decor: [], stand: [], stuff: [], sheet: { w: 0, h: 0, north: [0, 0], west: [0, 0], stuff: 0 } }

/** What a click on a figure or an exit offers, as the words a player would type to the DM. */
function offers(hit: Pick): { who: string; items: [string, string][] } {
  if (hit.kind === 'exit') return { who: titleCase(hit.name), items: [[`Go through the ${hit.name}`, `I go through the ${hit.name}.`]] }
  const name = titleCase(hit.id)
  return { who: name, items: [[`Talk to ${name}`, `I talk to ${name}.`], [`Look at ${name}`, `I look at ${name}.`]] }
}

/** The story set. `onAct`: sends words to the DM as this device's player (off when it may not speak). A click on a figure or an exit offers a few. */
export function StageView({ state, speaker, onAct }: { state: StageState; speaker?: string; onAct?: (text: string) => void }) {
  const [menu, setMenu] = useState<{ pick: Pick; left: number; top: number } | null>(null)
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
      onPick={
        onAct
          ? (hit, at) => {
              const skip = hit?.kind === 'actor' && state.actors[hit.id]?.side === 'party' // your own party is not someone to talk to
              setMenu(hit && !skip ? { pick: hit, ...at } : null)
            }
          : undefined
      }
      className="scene-in"
    >
      {menu && onAct && (
        <div className="absolute z-10 flex min-w-36 flex-col rounded border-2 border-[var(--border)] bg-black/90 p-1 text-[9px] pixel-font shadow-lg" style={{ left: `${menu.left}%`, top: `${menu.top}%` }}>
          <div className="px-2 py-1 text-[var(--dim)]">{offers(menu.pick).who}</div>
          {offers(menu.pick).items.map(([label, words]) => (
            <button
              key={label}
              type="button"
              className="rounded px-2 py-1 text-left hover:bg-white/10"
              onClick={() => {
                setMenu(null)
                onAct(words)
              }}
            >
              {label}
            </button>
          ))}
        </div>
      )}
    </SceneCanvas>
  )
}
