import { type PartyChar, ROMAN } from '@/lib/party'

export const TURN_KINDS = [
  { kind: 'action', label: 'Action', color: 'var(--action)' },
  { kind: 'bonus', label: 'Bonus Action', color: 'var(--bonus-action)' },
  { kind: 'reaction', label: 'Reaction', color: 'var(--reaction)' },
] as const

/** The three turn icons of Baldur's Gate 3: a green circle, an orange triangle, a purple four-point star. */
export function TurnShape({ kind, color, used }: { kind: 'action' | 'bonus' | 'reaction'; color: string; used: boolean }) {
  const paint = used ? { fill: 'none', stroke: 'var(--dim)', strokeWidth: 1.5 } : { fill: color, stroke: 'var(--ink)', strokeWidth: 1 }
  return (
    <svg viewBox="0 0 16 16" className="size-5" aria-hidden="true" opacity={used ? 0.6 : 1}>
      {kind === 'action' && <circle cx="8" cy="8" r="6" {...paint} />}
      {kind === 'bonus' && <polygon points="8,2 14.5,13.5 1.5,13.5" strokeLinejoin="round" {...paint} />}
      {kind === 'reaction' && <polygon points="8,1 10,6 15,8 10,10 8,15 6,10 1,8 6,6" strokeLinejoin="round" {...paint} />}
    </svg>
  )
}

/** Spell slots by level, one pip per slot: filled when it is still there, hollow when spent. */
export function SlotPips({ slots }: { slots: Record<string, { max: number; remaining: number }> }) {
  const levels = Object.keys(slots).filter((l) => slots[l].max > 0).sort((a, b) => Number(a) - Number(b))
  if (!levels.length) return null
  return (
    <ul className="flex flex-wrap gap-x-3 gap-y-1" aria-label="Spell slots">
      {levels.map((l) => {
        const { max, remaining } = slots[l]
        return (
          <li key={l} className="flex items-center gap-1" title={`Level ${l}: ${remaining} of ${max} slots left`}>
            <span className="pixel-font text-[8px] text-[var(--dim)]">{ROMAN[Number(l)]}</span>
            {Array.from({ length: max }, (_, i) => (
              <span
                key={i}
                className="size-2.5 border-2"
                style={{ borderColor: 'var(--slot)', background: i < remaining ? 'var(--slot)' : 'transparent' }}
              />
            ))}
          </li>
        )
      })}
    </ul>
  )
}


/** What a character has in a fight, in the icons of the party card: HP, the three turn icons, spell slots, class resources, conditions. */
export function CombatStatus({ c }: { c: PartyChar }) {
  const cur = c.hp.current ?? 0
  const max = c.hp.max || 1
  return (
    <div className="flex flex-col gap-1.5" aria-label={`${c.name}: status`}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <div className="flex min-w-24 flex-1 items-center gap-2">
          <div className="h-2.5 flex-1 border-2 border-[var(--border)] bg-black" role="img" aria-label={`${cur} of ${max} HP`}>
            <div className="h-full bg-[var(--ember)]" style={{ width: `${Math.min(100, (cur / max) * 100)}%` }} />
          </div>
          <span className="text-sm tabular-nums">
            {cur}/{max}
            {c.hp.temp ? ` +${c.hp.temp}` : ''}
          </span>
        </div>
        {TURN_KINDS.map(({ kind, label, color }) => {
          const used = c.turn[kind]
          return (
            <span key={kind} className="flex items-center gap-1 border-2 border-[var(--border)] px-1 py-0.5" title={`${label}: ${used ? 'used' : 'ready'}`}>
              <TurnShape kind={kind} color={color} used={used} />
              <span className="text-xs text-[var(--dim)]">{kind === 'bonus' ? 'Bonus' : label}</span>
            </span>
          )
        })}
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {c.spell && <SlotPips slots={c.spell.slots} />}
        {c.resources.map((r) => (
          <span key={r.name} className="flex items-center gap-1 text-xs" title={`${r.name}: comes back on a ${r.recharge} rest`}>
            {r.name}
            {Array.from({ length: r.max }, (_, i) => (
              <i key={i} className="size-2.5 border-2 border-[var(--ember)]" style={{ background: i >= r.max - r.used ? 'transparent' : 'var(--ember)' }} />
            ))}
          </span>
        ))}
        {c.conditions.map((k) => (
          <span key={k.name} className="border-2 px-1 text-xs leading-snug" style={{ borderColor: k.stance ? 'var(--good)' : 'var(--bad)', color: k.stance ? 'var(--good)' : 'var(--bad)' }}>
            {k.name}
          </span>
        ))}
      </div>
    </div>
  )
}
