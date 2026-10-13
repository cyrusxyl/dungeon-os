import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/8bit/button'
import { Settings, type Framework, type SettingsData } from '@/components/Settings'
import type { Mode } from '@/lib/view'

/** Settings during a game: the shared tabs without the DM tab. The DM is fixed while a session runs. */
export function SettingsPanel({ isHost, mode, onClose }: { isHost: boolean; mode: Mode; onClose: () => void }) {
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [frameworks, setFrameworks] = useState<Framework[]>([])
  const [loaded, setLoaded] = useState(!isHost) // a guest has nothing to load
  const [error, setError] = useState('')

  useEffect(() => {
    if (!isHost) return
    fetch('/api/menu')
      .then((r) => r.json())
      .then((m) => {
        setSettings(m.settings)
        setFrameworks(m.frameworks)
        setLoaded(true)
      })
      .catch(() => setError('Could not load the settings.'))
  }, [isHost])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div role="dialog" aria-label="Settings" className="fixed inset-0 z-50 grid place-items-center bg-black/80 p-3">
      <div className="flex max-h-full w-full max-w-md flex-col gap-4 overflow-y-auto border-4 border-[var(--gold)] bg-[var(--panel)] p-4">
        <h2 className="pixel-font text-xs text-[var(--gold)]">Settings</h2>
        {loaded ? (
          <Settings settings={settings} frameworks={frameworks} inGame mode={mode} onSaved={(m) => setSettings(m.settings)} />
        ) : (
          !error && <p className="text-[var(--dim)]">Loading…</p>
        )}
        {error && (
          <p role="alert" className="text-lg text-red-400">
            {error}
          </p>
        )}
        <p className="text-sm text-[var(--dim)]">To change the DM, end the session and open Settings from the main menu.</p>
        <Button variant="outline" onClick={onClose} className="text-[10px]">
          Close
        </Button>
      </div>
    </div>
  )
}
