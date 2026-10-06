// Who this device is: its public id, whether it is the host, and which seats it holds (server: stage/seats.py).
import { useEffect, useMemo, useState } from 'react'

import { deviceId, type StageState } from '@/lib/stage'

export interface Me {
  sid: string
  host: boolean
  /** Only the host gets it. Another device types it in to take over as the host (the table screen does). */
  hostCode: string | null
  /** Character ids this device plays. */
  mine: string[]
}

const key = (campaign: string, what: string) => `dungeon-${what}:${campaign}`

/** Per-campaign memory of this browser: which seats it took, and whether it chose to watch. Never required. */
export function recall(campaign: string, what: 'seats' | 'watching'): string[] | boolean {
  try {
    const raw = localStorage.getItem(key(campaign, what))
    return what === 'watching' ? raw === '1' : raw ? JSON.parse(raw) : []
  } catch {
    return what === 'watching' ? false : []
  }
}

export function remember(campaign: string, what: 'seats' | 'watching', value: string[] | boolean): void {
  try {
    localStorage.setItem(key(campaign, what), what === 'watching' ? (value ? '1' : '0') : JSON.stringify(value))
  } catch {
    /* private window: nothing is remembered */
  }
}

/** This device, read again when the host or the seats change. Null until the server answers. */
export function useMe(state: StageState | null): Me | null {
  const [me, setMe] = useState<{ sid: string; host: boolean; host_code: string | null } | null>(null)
  const version = `${state?.host}:${state?.seats.length}`
  useEffect(() => {
    if (!state) return
    let live = true
    fetch('/api/me', { headers: { 'X-Device': deviceId() } })
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null)
      .then((d) => live && d && setMe(d))
    return () => {
      live = false
    }
  }, [version, Boolean(state)])
  const seats = state?.seats
  const mine = useMemo(() => (seats ?? []).filter((s) => s.sid === me?.sid).map((s) => s.who), [seats, me?.sid])
  if (!me || !state) return null
  return { sid: me.sid, host: me.host, hostCode: me.host_code, mine }
}
