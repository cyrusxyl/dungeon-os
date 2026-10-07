import { useEffect, useRef, useState } from 'react'

import type { Notice } from '@/lib/stage'

const SHOW_MS = 6000

/** Item and gold changes for this device's characters. A notice that was already there on first load stays quiet. */
export function NoticeToasts({ notices, nameOf }: { notices: Notice[]; nameOf: (id: string) => string }) {
  const seen = useRef<Set<number> | null>(null)
  const [shown, setShown] = useState<Notice[]>([])
  useEffect(() => {
    if (seen.current === null) {
      seen.current = new Set(notices.map((n) => n.id))
      return
    }
    const fresh = notices.filter((n) => !seen.current!.has(n.id))
    if (!fresh.length) return
    fresh.forEach((n) => seen.current!.add(n.id))
    setShown((s) => [...s, ...fresh])
    const ids = new Set(fresh.map((n) => n.id))
    setTimeout(() => setShown((s) => s.filter((n) => !ids.has(n.id))), SHOW_MS)
  }, [notices])
  if (!shown.length) return null
  return (
    <div className="pointer-events-none fixed inset-x-2 top-2 z-40 flex flex-col items-end gap-2" aria-live="polite">
      {shown.map((n) => (
        <div key={n.id} role="status" className="max-w-xs border-4 border-[var(--gold)] bg-[var(--panel)] p-2 text-lg">
          <span className="pixel-font block text-[9px] text-[var(--gold)]">{nameOf(n.who)}</span>
          {n.lines.map((l) => (
            <span key={l} className={`block ${l.startsWith('−') ? 'text-[var(--bad)]' : 'text-[var(--good)]'}`}>
              {l}
            </span>
          ))}
        </div>
      ))}
    </div>
  )
}
