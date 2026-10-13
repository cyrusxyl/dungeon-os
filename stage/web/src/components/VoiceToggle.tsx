import { Button } from '@/components/ui/8bit/button'
import { setVoiceOn, setVoiceVolume, useSoundBlocked, useVoiceHealth, useVoiceOn, useVoiceVolume, unlock } from '@/lib/voice'
import type { Mode } from '@/lib/view'

/** This device: voice on or off, and volume. */
export function VoiceToggle({ mode }: { mode: Mode }) {
  const on = useVoiceOn(mode)
  const volume = useVoiceVolume()
  return (
    <div className="flex flex-col gap-2 text-lg">
      <div className="flex flex-wrap items-center gap-3">
        <Button size="sm" variant="outline" onClick={() => setVoiceOn(!on)} aria-pressed={on} title="Read the story aloud on this device." className="text-[10px]">
          {on ? 'Voice on' : 'Voice off'}
        </Button>
        <label className="flex items-center gap-2">
          Volume
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={volume}
            disabled={!on}
            onChange={(e) => setVoiceVolume(Number(e.target.value))}
            aria-label="Voice volume"
            className="w-28"
          />
        </label>
      </div>
    </div>
  )
}

/** The browser blocks sound until a click. The table screen taps once to allow it. */
export function SoundGate({ mode }: { mode: Mode }) {
  const on = useVoiceOn(mode)
  const blocked = useSoundBlocked()
  const { ok: healthy } = useVoiceHealth()
  if (mode !== 'table' || !on || !blocked || !healthy) return null
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/70">
      <Button onClick={() => void unlock()} className="text-sm">
        Enable sound
      </Button>
    </div>
  )
}
