// How this device shows rolls. Saved in the browser, so each device keeps its own choice. Nothing goes to the server.
import { useSyncExternalStore } from 'react'

import { readJson, write } from '@/lib/local'

export interface GameplayPrefs {
  /** `tray`: every die tumbles (the d20, then the damage dice in a tray). `text`: only the d20 tumbles. `off`: no roll window. */
  dice: 'tray' | 'text' | 'off'
  /** How the damage dice are thrown: after a short wait, or when the player clicks. */
  throw: 'auto' | 'click'
  speed: 'normal' | 'fast' | 'instant'
  /** How long the window stays open once everything has landed. */
  hold: 'short' | 'normal' | 'long' | 'click'
  /** Show the tiles that add to the roll. */
  tiles: boolean
  /** Show the 8-direction walking pad on the board of a fight. */
  pad: boolean
}

const DEFAULT_PREFS: GameplayPrefs = { dice: 'tray', throw: 'auto', speed: 'normal', hold: 'normal', tiles: true, pad: true }

const CHOICES: { [K in keyof GameplayPrefs]: readonly GameplayPrefs[K][] } = {
  dice: ['tray', 'text', 'off'],
  throw: ['auto', 'click'],
  speed: ['normal', 'fast', 'instant'],
  hold: ['short', 'normal', 'long', 'click'],
  tiles: [true, false],
  pad: [true, false],
}

const KEY = 'dungeon-gameplay'
function load(): GameplayPrefs {
  const saved = readJson<Record<string, unknown>>(KEY, {})
  const out = { ...DEFAULT_PREFS }
  for (const k of Object.keys(CHOICES) as (keyof GameplayPrefs)[]) {
    if ((CHOICES[k] as readonly unknown[]).includes(saved[k])) (out as Record<string, unknown>)[k] = saved[k]
  }
  return out
}

let current = load()
const listeners = new Set<() => void>()
const subscribe = (l: () => void) => {
  listeners.add(l)
  return () => void listeners.delete(l)
}

export function setPrefs(patch: Partial<GameplayPrefs>): void {
  current = { ...current, ...patch }
  write(KEY, JSON.stringify(current))
  listeners.forEach((l) => l())
}

export const usePrefs = (): GameplayPrefs => useSyncExternalStore(subscribe, () => current)

/** Window hold times, in ms. `click` never closes by itself. */
export const HOLD_MS: Record<GameplayPrefs['hold'], number> = { short: 2500, normal: 4500, long: 8000, click: Infinity }

export const reducedMotion = (): boolean => window.matchMedia('(prefers-reduced-motion: reduce)').matches

/** How long every animation takes, against its normal time. 0: no motion (the Instant choice, or a system that asks for less motion). */
export function timeScale(p: GameplayPrefs): number {
  if (reducedMotion()) return 0
  return { normal: 1, fast: 0.5, instant: 0 }[p.speed]
}
