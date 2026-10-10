import { Button } from '@/components/ui/8bit/button'
import { setVoiceOn, setVoiceVolume, useSoundBlocked, useVoiceHealth, useVoiceOn, useVoiceVolume, unlock } from '@/lib/voice'
import type { Mode } from '@/lib/view'

/** Mute button and volume for the narrator. Hidden when the server has no voice. */
export function VoiceToggle({ mode }: { mode: Mode }) {
  const healthy = useVoiceHealth()
  const on = useVoiceOn(mode)
  const volume = useVoiceVolume()
  if (!healthy) return null
  return (
    <span className="flex items-center gap-2 text-sm text-[var(--dim)]">
      <Button size="sm" variant="outline" onClick={() => setVoiceOn(!on)} aria-pressed={on} title="Read the story aloud." className="text-[10px]">
        {on ? 'Voice on' : 'Voice off'}
      </Button>
      {on && (
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={volume}
          onChange={(e) => setVoiceVolume(Number(e.target.value))}
          aria-label="Narrator volume"
          className="w-20"
        />
      )}
    </span>
  )
}

/** The browser blocks sound until a click. The table screen taps once to allow it. */
export function SoundGate({ mode }: { mode: Mode }) {
  const on = useVoiceOn(mode)
  const blocked = useSoundBlocked()
  const healthy = useVoiceHealth()
  if (mode !== 'table' || !on || !blocked || !healthy) return null
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/70">
      <Button onClick={() => void unlock()} className="text-sm">
        Enable sound
      </Button>
    </div>
  )
}
