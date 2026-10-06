import { Button } from '@/components/ui/8bit/button'
import { useHint } from '@/lib/hint'

/** The first screen on the device that starts a game: is it the shared screen, or a screen to play on? */
export function RoleScreen({ onTable, onPlay }: { onTable: () => void; onPlay: () => void }) {
  const { hint, tip } = useHint()
  return (
    <div role="dialog" aria-label="Set up this device" className="fixed inset-0 z-50 grid place-items-center bg-black/80 p-4">
      <div className="flex w-full max-w-md flex-col gap-3 border-4 border-[var(--gold)] bg-[var(--panel)] p-4">
        <h2 className="pixel-font text-xs text-[var(--gold)]">Set up this device</h2>
        <div className="flex flex-wrap gap-2">
          <Button onClick={onTable} {...tip('The shared screen for the room. It shows the story and a code that phones scan to join. Nobody plays on it.')} className="text-[10px]">
            Table screen
          </Button>
          <Button variant="outline" onClick={onPlay} {...tip('Play on this device. You can invite friends later with the Invite button.')} className="text-[10px]">
            Play here
          </Button>
        </div>
        <p className="min-h-10 text-sm text-[var(--dim)]" aria-live="polite">
          {hint || 'Point at a button to see what it does.'}
        </p>
      </div>
    </div>
  )
}
