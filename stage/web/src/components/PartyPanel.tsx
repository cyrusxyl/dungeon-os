import { memo, useState } from 'react'

import { Progress } from '@/components/ui/8bit/progress'
import { act, type CardAction, type EffectPreset, type Offer, type Party, type PartyChar, ROMAN, TONE } from '@/lib/party'

const TURN_KINDS = [
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

function Chip({ tone, children, title }: { tone: string; children: React.ReactNode; title?: string }) {
  return (
    <span className="inline-flex items-center gap-1 border-2 px-1.5 py-0.5 text-sm leading-none" style={{ borderColor: tone, color: tone }} title={title}>
      {children}
    </span>
  )
}

/** The bonuses a party member can really give (a spell they know, Bardic Inspiration). Empty menu: no button at all. */
export function GiveBonus({ offers, catalogue, onGive, kind }: { offers: Offer[]; catalogue: EffectPreset[]; onGive: (o: Offer) => void; kind?: string }) {
  const [open, setOpen] = useState(false)
  const choices = offers.map((o) => ({ o, e: catalogue.find((e) => e.id === o.effect) })).filter((x) => x.e && (!kind || x.e.on.includes(kind)))
  if (choices.length === 0) return null
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="border-2 border-dashed border-[var(--gold)] px-1.5 py-0.5 text-sm leading-none text-[var(--gold)] hover:bg-[var(--panel-2)]"
      >
        + Bonus
      </button>
      {/* In the flow, not floating: the party panel scrolls, and a floating menu would be cut off. */}
      {open && (
        <ul className="flex basis-full flex-col border-2 border-[var(--gold)] bg-[var(--ink)] text-left">
          {choices.map(({ o, e }) => (
            <li key={`${o.from}:${o.effect}`}>
              <button
                type="button"
                disabled={Boolean(o.why)}
                onClick={() => {
                  setOpen(false)
                  onGive(o)
                }}
                className="flex w-full flex-col px-2 py-1 text-left hover:bg-[var(--panel-2)] disabled:opacity-50"
              >
                <span style={{ color: TONE[e!.tone] }}>
                  {e!.label} <span className="text-xs text-[var(--dim)]">from {o.from_name} · {o.cost === 'bonus' ? 'bonus action' : 'action'}{o.slot ? ` · slot ${ROMAN[o.slot]}` : ''}</span>
                </span>
                <span className="text-xs text-[var(--dim)]">{o.why ?? e!.info}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

/** Action, bonus action and reaction: the game spends them, a player cannot toggle them. Dim outside a combat. */
function TurnPips({ c }: { c: PartyChar }) {
  return (
    <div className={`flex items-center gap-1 ${c.in_combat ? '' : 'opacity-50'}`} role="group" aria-label="This turn" title={c.in_combat ? undefined : 'Counted in a combat'}>
      {TURN_KINDS.map(({ kind, label, color }) => {
        const used = c.turn[kind]
        return (
          <span key={kind} className="flex items-center gap-1 border-2 border-[var(--border)] px-1.5 py-0.5" title={`${label}: ${used ? 'used' : 'ready'}`}>
            <TurnShape kind={kind} color={color} used={used} />
            <span className="text-xs text-[var(--dim)]">{kind === 'bonus' ? 'Bonus' : label}</span>
          </span>
        )
      })}
    </div>
  )
}

/** The common actions and class features. A greyed button says why; Attack and Shove ask for a target next. */
function Actions({ c, party, canAct, refresh }: { c: PartyChar; party: Party; canAct: boolean; refresh: () => void }) {
  const [picking, setPicking] = useState<{ action: CardAction; weapon?: string } | null>(null)
  const enemies = (party.combat?.order ?? []).filter((o) => !o.pc && o.health !== 'down')
  const run = (action: string, extra: Record<string, unknown> = {}) => {
    setPicking(null)
    act('/api/action', { who: c.id, action, ...extra }, refresh)
  }
  const click = (a: CardAction) => (a.target === 'enemy' ? setPicking({ action: a }) : run(a.id))
  const weapons = picking?.action.id === 'attack' && !picking.weapon && c.attacks.length > 1
  return (
    <section aria-label="Actions" className="flex flex-col gap-1">
      <h3 className="pixel-font text-[8px] text-[var(--dim)]">Actions</h3>
      <div className="flex flex-wrap gap-1">
        {c.actions.map((a) => {
          const off = Boolean(a.why) || !canAct
          return (
            <button
              key={a.id}
              type="button"
              disabled={off}
              onClick={() => click(a)}
              title={`${a.info}${a.why ? ` (${a.why})` : ''}`}
              className={`flex items-center gap-1 border-2 px-1.5 py-0.5 text-sm leading-none ${off ? 'border-[var(--border)] text-[var(--dim)] opacity-60' : 'border-[var(--border)] hover:border-[var(--gold)]'}`}
            >
              {a.cost && <TurnShape kind={a.cost} color={a.cost === 'action' ? 'var(--action)' : 'var(--bonus-action)'} used={false} />}
              {a.label}
            </button>
          )
        })}
      </div>
      {picking && (
        <div className="flex flex-col border-2 border-[var(--gold)] bg-[var(--ink)]">
          <div className="flex items-center justify-between px-2 py-1 text-sm text-[var(--gold)]">
            <span>{weapons ? `${picking.action.label} with…` : `${picking.action.label}: choose a target`}</span>
            <button type="button" onClick={() => setPicking(null)} className="pixel-font text-[8px] text-[var(--dim)] hover:text-[var(--parchment)]">
              Cancel
            </button>
          </div>
          {weapons
            ? c.attacks.map((w) => (
                <button key={w.name} type="button" onClick={() => setPicking({ ...picking, weapon: w.name })} className="flex justify-between px-2 py-1 text-left hover:bg-[var(--panel-2)]">
                  <span>{w.name}</span>
                  <span className="text-sm text-[var(--dim)]">
                    {w.bonus >= 0 ? '+' : ''}
                    {w.bonus} · {w.damage}
                  </span>
                </button>
              ))
            : enemies.map((o) => (
                <button key={o.id} type="button" onClick={() => run(picking.action.id, { target: o.id, weapon: picking.weapon })} className="flex justify-between px-2 py-1 text-left hover:bg-[var(--panel-2)]">
                  <span className="text-[var(--bad)]">{o.name}</span>
                  <span className="text-sm text-[var(--dim)]">{o.health}</span>
                </button>
              ))}
        </div>
      )}
    </section>
  )
}

function Card({ c, party, active, canAct, refresh, onSheet }: { c: PartyChar; party: Party; active: boolean; canAct: boolean; refresh: () => void; onSheet: () => void }) {
  const [portraitOk, setPortraitOk] = useState(true)
  const cur = c.hp.current ?? 0
  const max = c.hp.max || 1
  const catalogue = party.effects
  const held = c.effects.map((id) => catalogue.find((e) => e.id === id)).filter((e): e is EffectPreset => Boolean(e))
  return (
    <section className={`flex flex-col gap-2 border-2 p-2 ${active ? 'border-[var(--gold)] bg-[var(--panel-2)]' : 'border-[var(--border)]'}`}>
      <div className="flex gap-2">
        {portraitOk && (
          <img
            src={`/asset/actor/${encodeURIComponent(c.id)}/portrait/neutral.png`}
            alt=""
            className="pixelated size-12 shrink-0 border-2 border-[var(--border)] bg-black"
            onError={() => setPortraitOk(false)}
          />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2">
            <h2 className="pixel-font truncate text-[10px] text-[var(--gold)]">{c.name}</h2>
            <span className="text-sm text-[var(--dim)]">AC {c.armor_class}</span>
          </div>
          <p className="truncate text-sm text-[var(--dim)]">
            {c.race} {c.class} · lvl {c.level}
          </p>
          <div className="mt-1 flex items-center gap-2">
            <Progress value={(cur / max) * 100} variant="retro" className="h-3 flex-1" progressBg="bg-[var(--ember)]" />
            <span className="text-sm tabular-nums">
              {cur}/{max}
              {c.hp.temp ? ` +${c.hp.temp}` : ''}
            </span>
          </div>
        </div>
      </div>

      {active && (
        <div className="flex items-center justify-between gap-2 border-2 border-[var(--gold)] px-2 py-1">
          <span className="pixel-font text-[9px] text-[var(--gold)]">Your turn</span>
          <button
            type="button"
            disabled={!canAct}
            onClick={() => act('/api/end-turn', { who: c.id }, refresh)}
            className="pixel-font border-2 border-[var(--gold)] bg-[var(--gold)] px-2 py-1 text-[9px] text-[var(--ink)] hover:bg-[var(--parchment)] disabled:opacity-50"
          >
            End turn
          </button>
        </div>
      )}
      <TurnPips c={c} />
      <Actions c={c} party={party} canAct={canAct && (active || !c.in_combat)} refresh={refresh} />

      {c.spell && <SlotPips slots={c.spell.slots} />}

      {c.resources.length > 0 && (
        <ul className="flex flex-col gap-0.5">
          {c.resources.map((r) => (
            <li key={r.name} className="flex items-center justify-between gap-2 text-sm" title={`Comes back on a ${r.recharge} rest`}>
              <span className="truncate text-[var(--parchment)]/80">{r.name}</span>
              <span className="flex gap-1">
                {Array.from({ length: r.max }, (_, i) => {
                  const spent = i >= r.max - r.used
                  // A feature with an action button is spent by using it; one with none (Ki, Sorcery Points) is counted by hand.
                  if (c.actions.some((a) => a.id === `feature:${r.name}`)) {
                    return <span key={i} className="size-3 border-2 border-[var(--ember)]" style={{ background: spent ? 'transparent' : 'var(--ember)' }} />
                  }
                  return (
                    <button
                      key={i}
                      type="button"
                      aria-label={`${r.name}: ${spent ? 'spent, give back' : 'spend'}`}
                      onClick={() => act('/api/resource', { who: c.id, name: r.name, back: spent }, refresh)}
                      className="size-3 border-2 border-[var(--ember)]"
                      style={{ background: spent ? 'transparent' : 'var(--ember)' }}
                    />
                  )
                })}
              </span>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap items-center gap-1.5">
        {held.map((e) => (
          <Chip key={e.id} tone={TONE[e.tone]} title={e.concentration ? `${e.info} (a concentration spell)` : e.info}>
            {e.concentration && '◎ '}
            {e.label}
          </Chip>
        ))}
        {c.conditions.map((k) => (
          <Chip key={k.name} tone={k.stance ? 'var(--good)' : 'var(--bad)'}>
            {k.name}
          </Chip>
        ))}
        <GiveBonus offers={c.offers} catalogue={catalogue} onGive={(o) => act('/api/effects', { who: c.id, from: o.from, effect: o.effect }, refresh)} />
      </div>

      <button type="button" onClick={onSheet} className="pixel-font self-start text-[9px] text-[var(--dim)] hover:text-[var(--gold)]">
        Sheet · Items · Spells ▸
      </button>
    </section>
  )
}

/** The party: who acts now, each character's HP, turn actions, slots, bonuses, and a way into the sheet. */
export const PartyPanel = memo(function PartyPanel({ party, refresh, onSheet, canAct }: { party: Party | null; refresh: () => void; onSheet: (id: string) => void; canAct: boolean }) {
  if (!party) return null
  return (
    <aside className="flex w-full flex-col gap-3 overflow-y-auto border-4 border-[var(--border)] bg-[var(--panel)] p-3">
      {party.location && (
        <section>
          <h2 className="pixel-font text-[10px] text-[var(--gold)]">Where</h2>
          <p className="mt-1 text-lg">{party.location}</p>
          {party.game_time && <p className="text-[var(--dim)]">{party.game_time}</p>}
        </section>
      )}
      {party.characters.map((c) => (
        <Card key={c.id} c={c} party={party} active={party.combat?.current === c.id} canAct={canAct} refresh={refresh} onSheet={() => onSheet(c.id)} />
      ))}
      {party.quests.length > 0 && (
        <section>
          <h2 className="pixel-font text-[10px] text-[var(--gold)]">Quests</h2>
          <ul className="mt-1 text-sm">
            {party.quests.map((q) => (
              <li key={q.title}>
                • {q.title} <span className="text-[var(--dim)]">({q.status})</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </aside>
  )
})
