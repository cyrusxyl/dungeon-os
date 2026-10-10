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

const PINS = 3

/** The items a player keeps in the hand (up to three) for one character, on this device. Until the player chooses: the first three. */
export function usePins(who: string | null, items: string[]): [string[], (id: string) => void] {
  const key = `hand-pins:${who}`
  const [saved, setSaved] = useState<string[] | null>(() => {
    try {
      const raw = JSON.parse(localStorage.getItem(key) ?? 'null')
      return Array.isArray(raw) ? raw.filter((x): x is string => typeof x === 'string') : null
    } catch {
      return null
    }
  })
  const pinned = (saved ?? items).filter((id) => items.includes(id)).slice(0, PINS)
  const toggle = (id: string) => {
    const next = pinned.includes(id) ? pinned.filter((x) => x !== id) : [...pinned, id].slice(-PINS)
    setSaved(next)
    try {
      localStorage.setItem(key, JSON.stringify(next))
    } catch {
      /* a private window: the choice lasts until reload */
    }
  }
  return [pinned, toggle]
}
