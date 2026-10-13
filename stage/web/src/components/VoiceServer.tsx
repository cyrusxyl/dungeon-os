import { useCallback, useEffect, useState } from 'react'

import { Button } from '@/components/ui/8bit/button'
import { getJson, postJson } from '@/lib/stage'
import { setVoiceHealth } from '@/lib/voice'

interface TtsStatus {
  url: string
  reachable: boolean
  started_by_us: boolean
  starting: boolean
  failed: boolean
  can_start: boolean
}

/** The voice service: is it up, and start or stop it from here. `urlDirty`: the URL field has an unsaved change. */
export function VoiceServer({ urlDirty, stopOnExit }: { urlDirty: boolean; stopOnExit: boolean }) {
  const [st, setSt] = useState<TtsStatus | null>(null)
  const [checking, setChecking] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const apply = useCallback((s: TtsStatus) => {
    setSt(s)
    setVoiceHealth(s.reachable)
  }, [])

  const check = useCallback(async () => {
    setChecking(true)
    const s = await getJson<TtsStatus>('/api/tts/status') // on failure keep the last status
    if (s) apply(s)
    setChecking(false)
  }, [apply])

  useEffect(() => void check(), [check])

  // While the model loads, ask again every 2 seconds: a timeout chain, so requests never overlap. A hidden tab waits.
  const starting = st?.starting ?? false
  useEffect(() => {
    if (!starting) return
    let timer: number | undefined
    let stopped = false
    const tick = async () => {
      if (!document.hidden) await check()
      if (!stopped) timer = window.setTimeout(() => void tick(), 2000)
    }
    timer = window.setTimeout(() => void tick(), 2000)
    return () => {
      stopped = true
      window.clearTimeout(timer)
    }
  }, [starting, check])

  const act = async (what: 'start' | 'stop') => {
    setBusy(true)
    setError('')
    const res = await postJson(`/api/tts/${what}`, {})
    const body = await res.json().catch(() => null)
    if (res.ok) apply(body)
    else setError(body?.error ?? 'Could not do that.')
    setBusy(false)
  }

  const state = !st ? 'checking…' : st.reachable ? 'reachable' : st.starting ? 'starting…' : null
  return (
    <div className="flex flex-col gap-2 text-lg">
      <p className="flex flex-wrap items-center gap-2">
        Voice service: {state ?? <span className="text-[var(--bad)]">not reachable</span>}
        <Button size="sm" variant="outline" disabled={checking} onClick={() => void check()} className="text-[10px]">
          Check again
        </Button>
      </p>
      {st && (
        <>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={busy || !st.can_start || st.reachable || st.starting || urlDirty}
              onClick={() => void act('start')}
              className="text-[10px]"
            >
              Start voice server
            </Button>
            <Button size="sm" variant="outline" disabled={busy || !st.started_by_us} onClick={() => void act('stop')} className="text-[10px]">
              Stop voice server
            </Button>
          </div>
          {st.starting && <p className="text-sm text-[var(--dim)]">The model can take a minute to load.</p>}
          {st.failed && <p className="text-sm text-[var(--ember)]">The voice server stopped or did not answer. See tts/cache/service.log.</p>}
          {!st.can_start && !st.reachable && (
            <p className="text-sm text-[var(--dim)]">
              {st.url
                ? 'This URL is not on this machine, so the server cannot start it. Start it on that machine.'
                : 'Set the URL to start it from here. For example: http://127.0.0.1:8770'}
            </p>
          )}
          {urlDirty && st.can_start && <p className="text-sm text-[var(--dim)]">Save the new URL before you start the server.</p>}
          {st.started_by_us && (
            <p className="text-sm text-[var(--dim)]">
              This game server started it. {stopOnExit ? 'It stops when the game server stops.' : 'It keeps running when the game server stops.'}
            </p>
          )}
          {error && (
            <p role="alert" className="text-sm text-red-400">
              {error}
            </p>
          )}
        </>
      )}
    </div>
  )
}
