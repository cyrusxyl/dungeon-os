// How this device shows the game. Saved in the browser, so each device keeps its own choice.
//   player : a screen to play on. The layout follows the window: a large one shows the scene and the party, a small
//            one shows the story, the input and this player's cards (the scene is optional).
//   table  : the shared screen. It shows the story and the party. It has no input.
import { useCallback, useState, useSyncExternalStore } from 'react'

import { read, readJson, write } from '@/lib/local'

export type Mode = 'player' | 'table'
export type Layout = 'auto' | 'portrait' | 'landscape'
export interface HandOpts {
  scene: boolean
  layout: Layout
}

const MODES: Mode[] = ['player', 'table']
const LAYOUTS: Layout[] = ['auto', 'portrait', 'landscape']

/** The address can force a mode (`?view=table`); else the saved choice. `chosen` is false when neither is there. */
function firstMode(): { mode: Mode; chosen: boolean } {
  const raw = new URLSearchParams(location.search).get('view') ?? read('dungeon-view')
  const wanted = raw === 'full' || raw === 'hand' ? 'player' : raw // the two old player modes
  return MODES.includes(wanted as Mode) ? { mode: wanted as Mode, chosen: true } : { mode: 'player', chosen: false }
}

const wide = window.matchMedia('(min-width: 1024px)') // Tailwind `lg`
const watchWide = (l: () => void) => {
  wide.addEventListener('change', l)
  return () => wide.removeEventListener('change', l)
}
/** True on a window wide enough for the scene and the party panel together. */
export const useWide = (): boolean => useSyncExternalStore(watchWide, () => wide.matches)

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
