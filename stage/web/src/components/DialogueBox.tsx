import { useEffect, useRef, useState } from 'react'

import { focusOwnsKeys, type StoryLine, titleCase, useActorName } from '@/lib/stage'

const CHARS_PER_SECOND = 60

function Portrait({ actor, emotion, version }: { actor: string; emotion: string; version: number }) {
  const [failed, setFailed] = useState(false)
  useEffect(() => setFailed(false), [actor, emotion, version])
  return (
    <div className="grid size-24 shrink-0 place-items-center border-2 border-[var(--gold)] bg-[var(--panel-2)] sm:size-28">
      {failed ? (
        <span className="pixel-font text-lg text-[var(--dim)]">{titleCase(actor).slice(0, 1)}</span>
      ) : (
        <img
          src={`/asset/actor/${encodeURIComponent(actor)}/portrait/${emotion}.png?v=${version}`}
          alt={titleCase(actor)}
          className="pixelated h-full w-full object-contain"
          onError={() => setFailed(true)}
        />
      )}
    </div>
  )
}

/** Typewriter text that the player can finish early with a click. */
function useTypewriter(text: string, key: number): [string, boolean, () => void] {
  const [shown, setShown] = useState(0)
  useEffect(() => {
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduced) {
      setShown(text.length)
      return
    }
    setShown(0)
    const start = performance.now()
    let frame = 0
    const tick = (now: number) => {
      const n = Math.min(text.length, Math.floor(((now - start) / 1000) * CHARS_PER_SECOND))
      setShown(n)
      if (n < text.length) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [text, key])
  return [text.slice(0, shown), shown >= text.length, () => setShown(text.length)]
}

export function DialogueBox({
  line,
  pending,
  onAdvance,
  versions,
}: {
  line: StoryLine | undefined
  pending: number
  onAdvance: () => void
  versions: Record<string, number>
}) {
  const [typed, done, finish] = useTypewriter(line?.text ?? '', line?.seq ?? 0)
  const speaker = line?.type === 'say' ? line.actor : undefined
  const speakerName = useActorName(speaker, speaker ? versions[speaker] : 0)

  const click = () => {
    if (!done) finish()
    else if (pending > 0) onAdvance()
  }
  const clickRef = useRef(click)
  clickRef.current = click

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (focusOwnsKeys(e)) return
      if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault()
        clickRef.current()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  if (!line) {
    return <div className="min-h-32 border-4 border-[var(--gold)] bg-[var(--panel)] p-4 text-[var(--dim)]">…</div>
  }

  const speaking = line.type === 'say' && line.actor
  return (
    <button
      type="button"
      onClick={click}
      className="relative flex min-h-32 w-full gap-4 border-4 border-[var(--gold)] bg-[var(--panel)] p-3 text-left outline-none focus-visible:ring-2 focus-visible:ring-[var(--ember)] sm:p-4"
    >
      {speaking && <Portrait actor={line.actor!} emotion={line.emotion ?? 'neutral'} version={versions[line.actor!] ?? 0} />}
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        {speaking && <div className="pixel-font text-[10px] tracking-wider text-[var(--gold)]">{speakerName}</div>}
        <p className={`text-xl leading-snug sm:text-2xl ${speaking ? '' : 'italic text-[var(--parchment)]/90'}`}>{typed}</p>
      </div>
      {done && pending > 0 && (
        <span className="pixel-font absolute right-3 bottom-2 animate-pulse text-[10px] text-[var(--ember)]">▶ {pending}</span>
      )}
    </button>
  )
}
