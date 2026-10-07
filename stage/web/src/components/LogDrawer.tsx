import type { StoryLine } from '@/lib/stage'
import { useActorName } from '@/lib/stage'

type Feed = { seq: number; text: string }

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

/** Everything said on stage so far, and every roll beside it (the last 60 of each), to reread a missed line. */
export function LogDrawer({ open, onClose, log, feed }: { open: boolean; onClose: () => void; log: StoryLine[]; feed: Feed[] }) {
  if (!open) return null
  const entries: { seq: number; line?: StoryLine; feed?: Feed }[] = [...log.map((l) => ({ seq: l.seq, line: l })), ...feed.map((f) => ({ seq: f.seq, feed: f }))].sort((a, b) => a.seq - b.seq)
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
          {entries.length ? (
            entries.map((e) =>
              e.line ? (
                <Line key={`s${e.seq}`} line={e.line} />
              ) : (
                <p key={`f${e.seq}`} className="border-l-4 border-[var(--border)] pl-2 text-base text-[var(--ember)]">
                  {e.feed!.text}
                </p>
              ),
            )
          ) : (
            <p className="text-[var(--dim)]">Nothing has happened yet.</p>
          )}
        </div>
      </div>
    </aside>
  )
}
