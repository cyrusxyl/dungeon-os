// The server folds the stage events (stage/state.py) and sends the whole
// state after each change; the client only renders it.
import { useEffect, useRef, useState } from 'react'

/** True when a key press belongs to whatever has focus: inputs, the console, and every button. */
export function focusOwnsKeys(e: KeyboardEvent): boolean {
  return Boolean((e.target as HTMLElement).closest?.('input, textarea, select, button, a, [role=button], .xterm'))
}

/** True when the focus is a place to type text: arrows and letters belong to it. */
export function focusTakesText(e: KeyboardEvent): boolean {
  return Boolean((e.target as HTMLElement).closest?.('input, textarea, select, [contenteditable], .xterm'))
}

/**
 * JSON from a URL, fetched again when `version` changes. Undefined while the
 * first fetch runs; null when the server has nothing (or no URL).
 */
export function useJson<T>(url: string | null, version: number | string = 0): T | null | undefined {
  const [data, setData] = useState<{ url: string; value: T | null }>()
  useEffect(() => {
    if (!url) return
    let live = true
    fetch(url)
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null)
      .then((value) => live && setData({ url, value }))
    return () => {
      live = false
    }
  }, [url, version])
  if (!url) return null
  return data?.url === url ? data.value : undefined
}

/** The largest whole-number scale at which a w x h picture fits the element. */
export function useIntegerScale(ref: React.RefObject<HTMLDivElement | null>, w: number, h: number): number {
  const [scale, setScale] = useState(2)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect
      setScale(Math.max(1, Math.floor(Math.min(width / w, height / h))))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [ref, w, h])
  return scale
}

/** Display name from the actor file, e.g. "Sister Gareth"; the id until it loads. */
/** Display name from the actor file, e.g. "Sister Gareth"; the id until it loads. */
export function useActorName(id: string | undefined, version = 0): string {
  const data = useJson<{ name: string }>(id ? `/api/actor/${encodeURIComponent(id)}` : null, version)
  return data?.name ?? (id ? titleCase(id) : '')
}

export type Position = 'left' | 'center' | 'right' | 'far-left' | 'far-right'

export interface StoryLine {
  seq: number
  type: 'narrate' | 'say'
  text: string
  actor?: string
  emotion?: string
}

/** One seat: a player at a character. `sid` is a public id for the device; the device token never leaves it. */
export interface Seat {
  who: string
  player: string
  sid: string
  away: boolean
}

export interface StageState {
  seq: number
  scene: string | null
  actors: Record<string, { position: Position; emotion?: string }>
  log: StoryLine[]
  /** `who` set: the choices are for one player character (the server sends them to that player only). */
  choices: { options: string[]; seq: number; who?: string } | null
  dm: { status: 'starting' | 'busy' | 'idle' | 'waiting' | 'exited'; reason?: string; message?: string }
  dm_log: string[]
  versions: Record<string, number>
  rolls: Roll[]
  /** The DM asked a player character for a check or a save: the roll window waits for the player. */
  roll_request: RollRequest | null
  explore: string | null
  place: { map: string; place: string } | null
  creating: boolean
  party_mode: 'create' | 'premade'
  activity?: string[]
  /** The `sid` of the host's device, once there is one. */
  host: string | null
  seats: Seat[]
  /** The `sid` of the device that has the creator open; null while it is the host's. */
  creator: string | null
  /** Whispers from the DM to this device's characters. */
  private: { who: string; text: string; seq: number }[]
  /** The DM waits for answers: `who` is `all` or one character id. Names only, never the answers. */
  awaiting: { who: string; waiting: string[]; answered: string[] } | null}

/** One creature's roll in the roll window: the d20s, the tiles that add to it, and how it came out. */
export interface RollEntry {
  who: string
  name: string
  d20: number[]
  /** Index in `d20` of the die that counts. */
  kept: number
  mode: 'normal' | 'advantage' | 'disadvantage'
  mods: { label: string; value: number }[]
  bonus: { label: string; die: string; faces: number[]; value: number }[]
  total: number
  outcome: 'success' | 'fail' | 'hit' | 'miss' | 'crit' | 'fumble' | null
}

export interface RollDetail {
  kind: 'check' | 'save' | 'attack' | 'death'
  title: string
  subtitle: string
  /** Only when the players may see it (a hidden DC or a monster's AC is left out). */
  target?: { label: string; value: number }
  rolls: RollEntry[]
  damage?: { type: string; expr: string; faces: number[]; total: number }[]
}

export interface RollRequest {
  who: string
  name: string
  kind: 'check' | 'save'
  title: string
  subtitle: string
  dc?: number
  hide?: boolean
  /** What the roll is for (Hide, Shove): the DM reads it with the result. */
  note?: string
  mods: { label: string; value: number }[]
  seq: number
}

export interface Roll {
  expr: string
  total: number
  dice: { die: string; faces: number[] }[]
  /** Absent for a plain `uv run roll`: the window then shows only the dice. */
  detail?: RollDetail
  seq: number
}

/** This browser's private token. It tells the server which device asks; there is no password. */
export function deviceId(): string {
  try {
    let id = localStorage.getItem('dungeon-device')
    if (!id) {
      id = Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, '0')).join('')
      localStorage.setItem('dungeon-device', id)
    }
    return id
  } catch {
    return memoryId
  }
}
const memoryId = Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, '0')).join('')

function wsUrl(path: string): string {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${location.host}${path}`
}

/** Live stage state from /ws, with automatic reconnect. */
export function useStage(onNoGame: () => void): { state: StageState | null; campaign: string; connected: boolean } {
  const [state, setState] = useState<StageState | null>(null)
  const [campaign, setCampaign] = useState('')
  const [connected, setConnected] = useState(false)
  const retry = useRef(0)

  useEffect(() => {
    let ws: WebSocket | null = null
    let closed = false
    let timer: number | undefined

    const connect = () => {
      ws = new WebSocket(wsUrl(`/ws?d=${deviceId()}`))
      ws.onopen = () => {
        retry.current = 0
        setConnected(true)
      }
      ws.onmessage = (msg) => {
        const data = JSON.parse(msg.data)
        if (data.kind === 'snapshot') {
          setState(data.state)
          setCampaign(data.campaign)
        }
      }
      ws.onclose = async () => {
        setConnected(false)
        if (closed) return
        // The game may have ended (quit from another tab): then go to the menu.
        try {
          const menu = await (await fetch('/api/menu')).json()
          if (!menu.game) return onNoGame()
        } catch {
          /* server restarting: retry below */
        }
        retry.current = Math.min(retry.current + 1, 6)
        timer = window.setTimeout(connect, 300 * 2 ** retry.current)
      }
    }
    connect()
    return () => {
      closed = true
      window.clearTimeout(timer)
      ws?.close()
    }
  }, [])

  return { state, campaign, connected }
}

export function wsPtyUrl(): string {
  return wsUrl(`/ws/pty?d=${deviceId()}`)
}

/** POST as JSON: the server refuses any other POST (see LocalOnly in stage/server.py). */
export function postJson(url: string, body: unknown = {}): Promise<Response> {
  return fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Device': deviceId() },
    body: JSON.stringify(body),
  })
}

/** A line for the DM. `asHost` is a host control (End session): the DM gets it untagged. */
export async function sendInput(text: string, who?: string, asHost = false, whisper = false): Promise<Response> {
  return postJson('/api/input', { text, who, as_host: asHost, whisper })
}

export function titleCase(id: string): string {
  return id
    .split('#')[0]
    .split(/[-_]/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}
