// How this device shows the game. Saved in the browser, so each device keeps its own choice.
//   full  : the whole screen with the scene, the party and the input (solo play, and the default on a computer)
//   table : the shared screen. It shows the story and the party. It has no input.
//   hand  : a phone. It shows this player's character card and the input. The scene is optional.
import { useCallback, useState } from 'react'

import { read, readJson, write } from '@/lib/local'

export type Mode = 'full' | 'table' | 'hand'
export type Layout = 'auto' | 'portrait' | 'landscape'
export interface HandOpts {
  scene: boolean
  layout: Layout
}

const MODES: Mode[] = ['full', 'table', 'hand']
const LAYOUTS: Layout[] = ['auto', 'portrait', 'landscape']

/** A small screen is a hand and a large one is full. */
export const defaultMode = (): Mode => (window.innerWidth < 800 ? 'hand' : 'full')

/** The address can force a mode (`?view=table`); else the saved choice. `chosen` is false when neither is there. */
function firstMode(): { mode: Mode; chosen: boolean } {
  const wanted = new URLSearchParams(location.search).get('view') ?? read('dungeon-view')
  return MODES.includes(wanted as Mode) ? { mode: wanted as Mode, chosen: true } : { mode: defaultMode(), chosen: false }
}

function firstHand(): HandOpts {
  const saved = readJson<Partial<HandOpts>>('dungeon-hand', {})
  return { scene: Boolean(saved.scene), layout: LAYOUTS.includes(saved.layout as Layout) ? (saved.layout as Layout) : 'auto' }
}

export function useView() {
  const [first] = useState(firstMode)
  const [mode, setModeNow] = useState<Mode>(first.mode)
  const [chosen, setChosen] = useState(first.chosen)
  const [hand, setHandNow] = useState<HandOpts>(firstHand)
  const setMode = useCallback((m: Mode) => {
    setModeNow(m)
    setChosen(true)
    write('dungeon-view', m)
  }, [])
  const setHand = useCallback((h: HandOpts) => {
    setHandNow(h)
    write('dungeon-hand', JSON.stringify(h))
  }, [])
  return { mode, setMode, chosen, hand, setHand }
}
