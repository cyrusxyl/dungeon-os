// Who this device is: its public id, whether it is the host, and which seats it holds (server: stage/seats.py).
import { useEffect, useMemo, useState } from 'react'

import { read, readJson, write } from '@/lib/local'
import { deviceHeaders, type StageState } from '@/lib/stage'

export interface Me {
  sid: string
  host: boolean
  /** Only the host gets it. Another device types it in to take over as the host (the table screen does). */
  hostCode: string | null
  /** Character ids this device plays. */
  mine: string[]
}

/** Which seats this browser took in a campaign, so a reload sits back down at them. */
export const recallSeats = (campaign: string): string[] => readJson(`dungeon-seats:${campaign}`, [])
export const rememberSeats = (campaign: string, ids: string[]) => write(`dungeon-seats:${campaign}`, JSON.stringify(ids))

/** The player name this browser last used. */
export const savedName = () => read('dungeon-player-name') ?? ''
export const saveName = (name: string) => write('dungeon-player-name', name)

/** This device, read again when the host or the seats change. Null until the server answers. */
export function useMe(state: StageState | null): Me | null {
  const [me, setMe] = useState<{ sid: string; host: boolean; host_code: string | null } | null>(null)
  const version = `${state?.host}:${state?.seats.length}`
  useEffect(() => {
    if (!state) return
    let live = true
    fetch('/api/me', { headers: deviceHeaders() })
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
