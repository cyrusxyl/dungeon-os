// How this device shows the game. Saved in the browser, so each device keeps its own choice.
//   full  : the whole screen with the scene, the party and the input (solo play, and the default on a computer)
//   table : the shared screen. It shows the story and the party. It has no input.
//   hand  : a phone. It shows this player's character card and the input. The scene is optional.
import { useCallback, useState } from 'react'

export type Mode = 'full' | 'table' | 'hand'
export type Layout = 'auto' | 'portrait' | 'landscape'
export interface HandOpts {
  scene: boolean
  layout: Layout
}

const MODES: Mode[] = ['full', 'table', 'hand']
const DEFAULT_HAND: HandOpts = { scene: false, layout: 'auto' }

function read(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* private window: the choice lasts until the page closes */
  }
}

/** The address can force a mode (`?view=table`); else the saved choice; else a small screen is a hand and a large one is full. */
function firstMode(): Mode {
  const wanted = new URLSearchParams(location.search).get('view') ?? read('dungeon-view')
  if (MODES.includes(wanted as Mode)) return wanted as Mode
  return window.innerWidth < 800 ? 'hand' : 'full'
}

function firstHand(): HandOpts {
  try {
    const saved = JSON.parse(read('dungeon-hand') ?? '{}')
    return { scene: Boolean(saved.scene), layout: ['auto', 'portrait', 'landscape'].includes(saved.layout) ? saved.layout : 'auto' }
  } catch {
    return DEFAULT_HAND
  }
}

export function useView() {
  const [mode, setModeNow] = useState<Mode>(firstMode)
  const [hand, setHandNow] = useState<HandOpts>(firstHand)
  const setMode = useCallback((m: Mode) => {
    setModeNow(m)
    write('dungeon-view', m)
  }, [])
  const setHand = useCallback((h: HandOpts) => {
    setHandNow(h)
    write('dungeon-hand', JSON.stringify(h))
  }, [])
  return { mode, setMode, hand, setHand }
}
