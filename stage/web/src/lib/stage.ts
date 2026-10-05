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

export interface StageState {
  seq: number
  scene: string | null
  actors: Record<string, { position: Position; emotion?: string }>
  log: StoryLine[]
  choices: { options: string[]; seq: number } | null
  dm: { status: 'starting' | 'busy' | 'idle' | 'waiting' | 'exited'; reason?: string; message?: string }
  dm_log: string[]
  versions: Record<string, number>
  last_roll: Roll | null
  explore: string | null
  place: { map: string; place: string } | null
  creating: boolean
  party_mode: 'create' | 'premade'
  activity?: string[]
}

export interface Roll {
  expr: string
  total: number
  dice: { die: string; faces: number[] }[]
  seq: number
}

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
      ws = new WebSocket(wsUrl('/ws'))
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
  return wsUrl('/ws/pty')
}

/** POST as JSON: the server refuses any other POST (see LocalOnly in stage/server.py). */
export function postJson(url: string, body: unknown = {}): Promise<Response> {
  return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
}

export async function sendInput(text: string): Promise<void> {
  await postJson('/api/input', { text })
}

export function titleCase(id: string): string {
  return id
    .split('#')[0]
    .split(/[-_]/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}
