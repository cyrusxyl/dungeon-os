import { useEffect, useRef, useState } from 'react'

import { DiceOverlay } from '@/components/DiceOverlay'
import { DmTable } from '@/components/DmTable'
import { type Position, type StageState, titleCase, useIntegerScale, useJson } from '@/lib/stage'

// Logical stage size in source pixels: a 10 x 6 room of 32 px LPC tiles.
export const STAGE_W = 320
export const STAGE_H = 192
const FRAME = 64
const FLOOR_Y = 100
const SLOT_X: Record<Position, number> = {
  'far-left': 8,
  left: 56,
  center: 128,
  right: 200,
  'far-right': 248,
}

function Img({ src, fallback, className }: { src: string; fallback: React.ReactNode; className?: string }) {
  const [failed, setFailed] = useState(false)
  useEffect(() => setFailed(false), [src])
  if (failed) return <>{fallback}</>
  return <img src={src} alt="" draggable={false} className={`pixelated ${className ?? ''}`} onError={() => setFailed(true)} />
}

// A big monster's PNG is bigger than the 64 px frame: draw it at its own size, centered on its slot, feet on the floor line.
function ActorSprite({ id, src, x, lift, filter }: { id: string; src: string; x: number; lift: number; filter: string }) {
  const [size, setSize] = useState(FRAME)
  const [failed, setFailed] = useState(false)
  useEffect(() => setFailed(false), [src])
  return (
    <div
      className="absolute transition-[left] duration-300"
      style={{ left: Math.max(0, Math.min(STAGE_W - size, x - (size - FRAME) / 2)), top: FLOOR_Y + FRAME - size - lift, width: size, height: size, filter }}
    >
      {failed ? (
        <Silhouette id={id} />
      ) : (
        <img
          src={src}
          alt=""
          draggable={false}
          className="pixelated h-full w-full"
          onLoad={(e) => setSize(Math.max(FRAME, e.currentTarget.naturalWidth))}
          onError={() => setFailed(true)}
        />
      )}
    </div>
  )
}

function Silhouette({ id }: { id: string }) {
  // Shown until an actor has an appearance: a plain figure shape, never a guess.
  return (
    <svg viewBox="0 0 64 64" className="h-full w-full" aria-hidden="true">
      <ellipse cx="32" cy="60" rx="12" ry="3" fill="#000" opacity="0.35" />
      <circle cx="32" cy="22" r="8" fill="#3a3350" />
      <rect x="22" y="31" width="20" height="26" rx="3" fill="#3a3350" />
      <title>{titleCase(id)}</title>
    </svg>
  )
}

// Actors are drawn over the scene image, so they get the scene's mood as a filter.
const MOOD_FILTER: Record<string, string> = {
  day: 'none',
  dusk: 'sepia(0.2) brightness(0.92)',
  night: 'brightness(0.6) saturate(0.7) hue-rotate(10deg)',
  torchlit: 'brightness(0.8) sepia(0.25)',
  fog: 'contrast(0.85) brightness(1.05) saturate(0.8)',
  rain: 'brightness(0.75) saturate(0.8)',
  snow: 'brightness(1.03) saturate(0.85)',
}

function useMood(scene: string | null, version: number): string {
  return useJson<{ mood: string }>(scene ? `/api/scene/${encodeURIComponent(scene)}` : null, version)?.mood ?? 'day'
}

export function StageView({ state, speaker }: { state: StageState; speaker?: string }) {
  const box = useRef<HTMLDivElement>(null)
  const scale = useIntegerScale(box, STAGE_W, STAGE_H)
  const scene = state.scene
  const mood = useMood(scene, state.versions?.[`scene:${scene}`] ?? 0)

  return (
    <div ref={box} className="relative flex h-full w-full items-center justify-center overflow-hidden">
      <DiceOverlay rolls={state.rolls} />
      <div
        className="relative shrink-0 overflow-hidden"
        style={{ width: STAGE_W, height: STAGE_H, transform: `scale(${scale})`, transformOrigin: 'center' }}
      >
        <div className="absolute inset-0" style={{ background: 'linear-gradient(#221d30 0 52%, #2c2536 52% 100%)' }} />
        {scene && (
          <Img
            key={scene}
            src={`/asset/scene/${scene}.png?v=${state.versions?.[`scene:${scene}`] ?? 0}`}
            className="scene-in absolute inset-0 h-full w-full"
            fallback={
              <div className="absolute inset-x-0 top-6 text-center text-[8px] tracking-wider text-[var(--dim)] pixel-font">
                {titleCase(scene)}
              </div>
            }
          />
        )}
        {Object.entries(state.actors).map(([id, actor]) => {
          const x = SLOT_X[actor.position] ?? SLOT_X.center
          const talking = id === speaker
          return (
            <ActorSprite
              key={id}
              id={id}
              src={`/asset/actor/${encodeURIComponent(id)}/full.png?f=${actor.position}&v=${state.versions?.[id] ?? 0}`}
              x={x}
              lift={talking ? 2 : 0}
              filter={MOOD_FILTER[mood] ?? 'none'}
            />
          )
        })}
        {!scene && Object.keys(state.actors).length === 0 &&
          (state.dm.status === 'starting' || state.dm.status === 'busy' ? (
            <DmTable activity={state.activity} />
          ) : (
            <div className="absolute inset-0 grid place-items-center text-[8px] text-[var(--dim)] pixel-font">No scene yet</div>
          ))}
      </div>
    </div>
  )
}
