import { useState } from 'react'

import { BAND_FILL, type Entrant, type Party } from '@/lib/party'

const TEAM_BORDER = { party: 'border-[var(--good)]', neutral: 'border-[var(--gold)]', hostile: 'border-[var(--bad)]' } as const
const TEAM_COLOR = { party: 'var(--good)', neutral: 'var(--gold)', hostile: 'var(--bad)' } as const

/** One place in the turn order: a portrait, its initiative, and how hurt it is (a band for a creature, the real bar for a player character). */
function Slot({ o, party, current, compact }: { o: Entrant; party: Party; current: boolean; compact: boolean }) {
  const [portraitOk, setPortraitOk] = useState(true)
  const pc = party.characters.find((c) => c.id === o.id)
  const fill = pc ? Math.round(((pc.hp.current ?? 0) / (pc.hp.max || 1)) * 100) : BAND_FILL[o.health]
  const hurt = pc ? `${pc.hp.current}/${pc.hp.max} HP` : o.health
  const conditions = o.conditions.map((k) => k.name)
  return (
    <li
      aria-current={current ? 'step' : undefined}
      title={`${o.name}: ${hurt}${conditions.length ? ` · ${conditions.join(', ')}` : ''}`}
      className={`flex ${compact ? 'w-12' : 'w-16'} shrink-0 flex-col items-center gap-0.5 border-2 p-1 ${current ? 'border-[var(--gold)] bg-[var(--panel-2)]' : 'border-[var(--border)]'} ${o.health === 'down' ? 'opacity-50' : ''}`}
    >
      <div className="relative">
        {portraitOk ? (
          <img
            src={`/asset/actor/${encodeURIComponent(o.id)}/portrait/neutral.png`}
            alt=""
            className={`pixelated ${compact ? 'size-7' : 'size-10'} border-2 bg-black ${TEAM_BORDER[o.team]}`}
            onError={() => setPortraitOk(false)}
          />
        ) : (
          <div className={`pixel-font grid ${compact ? 'size-7' : 'size-10'} place-items-center border-2 bg-black text-xs ${TEAM_BORDER[o.team]}`}>{o.name.charAt(0)}</div>
        )}
        <span className="pixel-font absolute -right-1 -bottom-1 bg-[var(--ink)] px-0.5 text-[8px] text-[var(--gold)]">{o.initiative}</span>
      </div>
      <span className="w-full truncate text-center text-xs leading-none">{o.name}</span>
      <div className="h-1.5 w-full border border-[var(--border)] bg-black" role="img" aria-label={hurt}>
        <div className="h-full" style={{ width: `${fill}%`, background: TEAM_COLOR[o.team] }} />
      </div>
      {!compact && <span className={`w-full truncate text-center text-[10px] leading-none ${conditions.length ? 'text-[var(--ember)]' : 'text-[var(--dim)]'}`}>
        {conditions.length ? conditions.join(', ') : pc ? ' ' : o.health}
      </span>}
    </li>
  )
}

/**
 * The turn order across the top of a combat, like Baldur's Gate 3's initiative bar. The turn in play is lit;
 * a creature shows how hurt it is as a bar and a word, never as numbers.
 */
export function TurnBar({ party, dmStatus, feed, compact = false }: { party: Party; dmStatus: string; feed: { seq: number; text: string }[]; compact?: boolean }) {
  const combat = party.combat
  if (!combat) return null
  const now = combat.order.find((o) => o.id === combat.current)
  const yours = Boolean(now?.pc)
  return (
    <section aria-label="Turn order" className={`flex items-stretch ${compact ? 'gap-2 border-2 p-1' : 'gap-3 border-4 p-2'} border-[var(--border)] bg-[var(--panel)]`}>
      <div className={`flex ${compact ? 'w-9' : 'w-28'} shrink-0 flex-col justify-center`}>
        <h2 className="pixel-font text-[10px] text-[var(--gold)]">{compact ? `R${combat.round}` : `Round ${combat.round}`}</h2>
        {now && !compact && (
          <p className={`text-sm leading-tight ${yours ? 'text-[var(--gold)]' : 'text-[var(--bad)]'}`}>
            {yours ? `${now.name}'s turn` : `${now.name} acts`}
            {!yours && dmStatus === 'busy' ? '…' : ''}
          </p>
        )}
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <ol className="flex min-w-0 gap-1.5 overflow-x-auto">
          {combat.order.map((o) => (
            <Slot key={o.id} o={o} party={party} current={o.id === combat.current} compact={compact} />
          ))}
        </ol>
        {/* What just happened: an enemy's attack and its damage, in words, on every screen. */}
        <ul aria-label="What just happened" aria-live="polite" className="flex flex-col text-sm leading-tight text-[var(--parchment)]">
          {feed.slice(compact ? -1 : -2).map((f) => (
            <li key={f.seq} className="truncate">
              {f.text}
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}
