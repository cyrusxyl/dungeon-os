import { useEffect, useState } from 'react'

import type { HandView } from '@/lib/arena'
import { deviceHeaders } from '@/lib/stage'

export type Skin = 'cards' | 'list'

const SKIN_KEY = 'hand-skin'

/** The skin is a choice of the player, kept on this device. */
export function useSkin(): [Skin, () => void] {
  const [skin, setSkin] = useState<Skin>(() => {
    try {
      return localStorage.getItem(SKIN_KEY) === 'list' ? 'list' : 'cards'
    } catch {
      return 'cards'
    }
  })
  const flip = () =>
    setSkin((s) => {
      const next = s === 'cards' ? 'list' : 'cards'
      try {
        localStorage.setItem(SKIN_KEY, next)
      } catch {
        /* a private window: the choice lasts until reload */
      }
      return next
    })
  return [skin, flip]
}

/** The hand of a character, fetched again each time the board changes. */
export function useHand(who: string | null, version: number | string): HandView | null {
  const [hand, setHand] = useState<{ key: string; value: HandView | null }>()
  const key = `${who}:${version}`
  useEffect(() => {
    if (!who) return
    let live = true
    fetch(`/api/arena/hand?who=${encodeURIComponent(who)}`, { headers: deviceHeaders() })
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null)
      .then((value) => live && setHand({ key, value }))
    return () => {
      live = false
    }
  }, [who, key])
  return who && hand?.key === key ? hand.value : null
}
