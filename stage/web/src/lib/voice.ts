// Narration voice. The stage server streams raw PCM16 mono from /api/tts/line/{seq}.
// Chunks play back to back on one AudioContext. If the server has no voice, nothing plays.
import { useEffect, useState, useSyncExternalStore } from 'react'

import { read, readJson, write } from '@/lib/local'
import type { Mode } from '@/lib/view'
import type { StoryLine } from '@/lib/stage'

let ctx: AudioContext | null = null
let gain: GainNode | null = null
let abort: AbortController | null = null

const listeners = new Set<() => void>()
const emit = () => listeners.forEach((l) => l())
const subscribe = (l: () => void) => {
  listeners.add(l)
  return () => void listeners.delete(l)
}

/** Saved choice, or null when this device never chose. */
export const savedVoiceOn = (): boolean | null => {
  const v = read('voice-on')
  return v === null ? null : v === '1'
}
export const savedVolume = (): number => {
  const v = Number(readJson<number | string>('voice-volume', 0.8))
  return Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : 0.8
}

export function setVoiceOn(on: boolean): void {
  write('voice-on', on ? '1' : '0')
  if (on) void unlock()
  else stop()
  emit()
}

export function setVoiceVolume(v: number): void {
  write('voice-volume', String(v))
  if (gain) gain.gain.value = v
  emit()
}

function makeGain(c: AudioContext): GainNode {
  const g = c.createGain()
  g.gain.value = savedVoiceOn() === false ? 0 : savedVolume()
  g.connect(c.destination)
  return g
}

function audio(): AudioContext {
  if (!ctx) {
    // Run the context at the stream rate: a browser resamples every small buffer on its own, and each edge clicks.
    ctx = new AudioContext({ sampleRate: 24000 })
    gain = makeGain(ctx)
    ctx.onstatechange = emit
  }
  return ctx
}

/** Resume the AudioContext. The browser allows this only after a click or tap. */
export async function unlock(): Promise<void> {
  try {
    await audio().resume()
  } catch {
    /* stays silent */
  }
  emit()
}

export function stop(): void {
  abort?.abort()
  abort = null
  // Drop what is already scheduled by replacing the gain node.
  if (ctx && gain) {
    gain.disconnect()
    gain = makeGain(ctx)
  }
}

/** Fetch line `seq` and schedule its chunks back to back. Any earlier line stops first. */
export async function play(seq: number): Promise<void> {
  stop()
  const ac = new AbortController()
  abort = ac
  try {
    const res = await fetch(`/api/tts/line/${seq}`, { signal: ac.signal })
    if (res.status !== 200 || !res.body) return
    const rate = Number(res.headers.get('X-Sample-Rate')) || 24000
    const a = audio()
    const out = gain!
    let at = 0
    let spare: number[] = []
    const reader = res.body.getReader()
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      // A chunk can end in the middle of a 2-byte sample.
      const bytes = spare.length ? Uint8Array.from([...spare, ...value]) : value
      const n = bytes.length >> 1
      spare = bytes.length & 1 ? [bytes[bytes.length - 1]] : []
      if (!n) continue
      const view = new DataView(bytes.buffer, bytes.byteOffset, n * 2)
      const buf = a.createBuffer(1, n, rate)
      const ch = buf.getChannelData(0)
      for (let i = 0; i < n; i++) ch[i] = view.getInt16(i * 2, true) / 32768
      const src = a.createBufferSource()
      src.buffer = buf
      src.connect(out)
      at = Math.max(at, a.currentTime + 0.05)
      src.start(at)
      at += buf.duration
    }
  } catch {
    /* aborted, or the server is down: stay silent */
  }
}

/** Whether this device wants voice. The table defaults to on; other modes default to off. */
export function useVoiceOn(mode: Mode): boolean {
  return useSyncExternalStore(subscribe, () => savedVoiceOn() ?? mode === 'table')
}

export function useVoiceVolume(): number {
  return useSyncExternalStore(subscribe, savedVolume)
}

/** True while the browser blocks sound until a click. */
export function useSoundBlocked(): boolean {
  return useSyncExternalStore(subscribe, () => ctx === null || ctx.state !== 'running')
}

/** True when the server has a voice. */
export function useVoiceHealth(): boolean {
  const [ok, setOk] = useState(false)
  useEffect(() => {
    let live = true
    fetch('/api/tts/health')
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => live && setOk(Boolean(j?.ok)))
      .catch(() => live && setOk(false))
    return () => {
      live = false
    }
  }, [])
  return ok
}

/** Say the current beat (narration or speech). The server stays silent for a speaker with no voice. */
export function useNarration(current: StoryLine | undefined, enabled: boolean): void {
  const seq = current ? current.seq : undefined
  useEffect(() => {
    stop()
    if (enabled && seq !== undefined) void play(seq)
    return stop
  }, [seq, enabled])
}
