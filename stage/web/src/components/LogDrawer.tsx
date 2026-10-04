import type { StoryLine } from '@/lib/stage'
import { useActorName } from '@/lib/stage'

function Line({ line }: { line: StoryLine }) {
  const name = useActorName(line.type === 'say' ? line.actor : undefined)
  return line.type === 'say' ? (
    <p>
      <span className="pixel-font mr-2 text-[10px] text-[var(--gold)]">{name}</span>
      {line.text}
    </p>
  ) : (
    <p className="italic text-[var(--parchment)]/80">{line.text}</p>
  )
}

/** Everything said on stage so far (the last 60 lines), to reread a missed line. */
export function LogDrawer({ open, onClose, log }: { open: boolean; onClose: () => void; log: StoryLine[] }) {
  if (!open) return null
  return (
    <aside className="fixed inset-y-0 right-0 z-40 flex w-full max-w-md flex-col border-l-4 border-[var(--gold)] bg-[var(--ink)]">
      <div className="flex items-center border-b-2 border-[var(--border)] px-4 py-3">
        <h2 className="pixel-font text-[10px] text-[var(--gold)]">Story so far</h2>
        <button type="button" onClick={onClose} className="pixel-font ml-auto text-[10px] text-[var(--dim)] hover:text-[var(--parchment)]">
          Close ✕
        </button>
      </div>
      <div className="flex flex-1 flex-col-reverse overflow-y-auto px-4 py-3">
        <div className="flex flex-col gap-3 text-lg leading-snug">
          {log.length ? log.map((l) => <Line key={l.seq} line={l} />) : <p className="text-[var(--dim)]">Nothing has happened yet.</p>}
        </div>
      </div>
    </aside>
  )
}
