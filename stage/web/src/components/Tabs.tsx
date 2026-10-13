import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'

export interface Tab {
  id: string
  label: string
  body: ReactNode
}

/** Tabs with the keyboard pattern: arrows, Home and End move; every panel stays mounted so nothing is lost. */
export function Tabs({ tabs, label }: { tabs: Tab[]; label: string }) {
  const base = useId()
  const [active, setActive] = useState(tabs[0].id)
  const buttons = useRef<Record<string, HTMLButtonElement | null>>({})
  if (tabs.length === 1) return <>{tabs[0].body}</>

  const go = (i: number) => {
    const t = tabs[(i + tabs.length) % tabs.length]
    setActive(t.id)
    buttons.current[t.id]?.focus()
  }
  const onKey = (e: KeyboardEvent, i: number) => {
    const to = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key]
    if (to === undefined) return
    e.preventDefault()
    go(to)
  }
  return (
    <div className="flex flex-col gap-3">
      <div role="tablist" aria-label={label} className="flex border-b-4 border-[var(--border)]">
        {tabs.map((t, i) => (
          <button
            key={t.id}
            ref={(el) => void (buttons.current[t.id] = el)}
            type="button"
            role="tab"
            id={`${base}-tab-${t.id}`}
            aria-selected={active === t.id}
            aria-controls={`${base}-panel-${t.id}`}
            tabIndex={active === t.id ? 0 : -1}
            onClick={() => setActive(t.id)}
            onKeyDown={(e) => onKey(e, i)}
            className={`pixel-font min-w-0 flex-1 px-2 py-2 text-[10px] ${active === t.id ? 'bg-[var(--ink)] text-[var(--gold)]' : 'text-[var(--dim)] hover:text-[var(--parchment)]'}`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tabs.map((t) => (
        <div
          key={t.id}
          role="tabpanel"
          id={`${base}-panel-${t.id}`}
          aria-labelledby={`${base}-tab-${t.id}`}
          hidden={active !== t.id}
          className="flex flex-col gap-3"
        >
          {t.body}
        </div>
      ))}
    </div>
  )
}
