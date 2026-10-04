import { useEffect, useRef, useState } from 'react'

import { DiceOverlay } from '@/components/DiceOverlay'
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
      <DiceOverlay roll={state.last_roll ?? null} />
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
            <div
              key={id}
              className="absolute transition-[left] duration-300"
              style={{ left: x, top: FLOOR_Y - (talking ? 2 : 0), width: FRAME, height: FRAME, filter: MOOD_FILTER[mood] ?? 'none' }}
            >
              <Img src={`/asset/actor/${encodeURIComponent(id)}/full.png?f=${actor.position}&v=${state.versions?.[id] ?? 0}`} fallback={<Silhouette id={id} />} className="h-full w-full" />
            </div>
          )
        })}
        {!scene && Object.keys(state.actors).length === 0 && (
          <div className="absolute inset-0 grid place-items-center text-[8px] text-[var(--dim)] pixel-font">
            {state.dm.status === 'starting' ? 'The DM sets the table…' : 'No scene yet'}
          </div>
        )}
      </div>
    </div>
  )
}
