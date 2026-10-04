// Mirror of stage/state.py: the server sends one snapshot, then events, and
// the client folds them with the same rules so both sides agree.
import { useEffect, useRef, useState } from 'react'

const names = new Map<string, Promise<string>>()

/** Display name from the actor file, e.g. "Sister Gareth"; the id until it loads. */
export function useActorName(id: string | undefined): string {
  const [name, setName] = useState(id ? titleCase(id) : '')
  useEffect(() => {
    if (!id) return
    setName(titleCase(id))
    if (!names.has(id)) {
      names.set(
        id,
        fetch(`/api/actor/${encodeURIComponent(id)}`)
          .then((r) => r.json())
          .then((d) => d.name as string)
          .catch(() => titleCase(id)),
      )
    }
    let live = true
    names.get(id)!.then((n) => live && setName(n))
    return () => {
      live = false
    }
  }, [id])
  return name
}

/** Forget cached names, e.g. after the DM changes an actor. */
export function forgetActorName(id: string): void {
  names.delete(id)
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
}

export interface Roll {
  expr: string
  total: number
  dice: { die: string; faces: number[] }[]
  seq: number
}

export type StageEvent = Record<string, unknown> & { type: string; seq: number }

const AUTO: Position[] = ['left', 'right', 'center', 'far-left', 'far-right']

function freePosition(actors: StageState['actors']): Position {
  const taken = new Set(Object.values(actors).map((a) => a.position))
  return AUTO.find((p) => !taken.has(p)) ?? 'center'
}

export function apply(state: StageState, e: StageEvent): StageState {
  const s: StageState = { ...state, seq: e.seq, actors: { ...state.actors } }
  switch (e.type) {
    case 'scene':
      return { ...s, scene: e.location as string, actors: {}, choices: null }
    case 'enter':
      s.actors[e.actor as string] = {
        position: (e.position as Position) ?? freePosition(s.actors),
        emotion: 'neutral',
      }
      return s
    case 'exit':
      delete s.actors[e.actor as string]
      return s
    case 'clear':
      return { ...s, actors: {} }
    case 'narrate':
    case 'say': {
      if (e.type === 'say') {
        const id = e.actor as string
        s.actors[id] = { position: s.actors[id]?.position ?? freePosition(s.actors), emotion: (e.emotion as string) ?? 'neutral' }
      }
      const line = { ...(e as unknown as StoryLine), seq: e.seq }
      return { ...s, log: [...s.log, line].slice(-60), choices: null }
    }
    case 'choices':
      return { ...s, choices: { options: e.options as string[], seq: e.seq } }
    case 'roll':
      return { ...s, last_roll: { expr: e.expr as string, total: e.total as number, dice: (e.dice as Roll['dice']) ?? [], seq: e.seq } }
    case 'scene_updated':
      return { ...s, versions: { ...(s.versions ?? {}), [`scene:${e.location as string}`]: e.seq } }
    case 'actor_updated':
      return { ...s, versions: { ...(s.versions ?? {}), [e.actor as string]: e.seq } }
    case 'dm_status': {
      const dm = { status: e.status, reason: e.reason, message: e.message } as StageState['dm']
      const dm_log = e.dm_text ? [...s.dm_log, e.dm_text as string].slice(-30) : s.dm_log
      return { ...s, dm, dm_log }
    }
    default:
      return s
  }
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
        } else if (data.kind === 'event') {
          if (data.event.type === 'actor_updated') forgetActorName(data.event.actor)
          setState((s) => (s ? apply(s, data.event) : s))
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
