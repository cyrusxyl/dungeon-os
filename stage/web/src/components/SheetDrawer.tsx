import { useState } from 'react'

import { SlotPips } from '@/components/PartyPanel'
import { type Item, type Party, type PartyChar, ROMAN, signed } from '@/lib/party'
import { titleCase, useJson } from '@/lib/stage'

type Tab = 'sheet' | 'items' | 'spells'

// Rarity colours follow the usual game order: grey, green, blue, purple, orange.
const RARITY: Record<string, string> = {
  common: '#c8c3d4',
  uncommon: '#5fcf6f',
  rare: '#5aa9ff',
  'very rare': '#b36bff',
  legendary: '#f08a24',
}

const PROF_MARK = ['○', '●', '◆']
const PROF_TEXT = ['not proficient', 'proficient', 'expertise']

/** The character sheet, the backpack and the spellbook, like the three panels of Baldur's Gate 3's character screen. */
export function SheetDrawer({ party, who, onWho, onClose }: { party: Party; who: string; onWho: (id: string) => void; onClose: () => void }) {
  const [tab, setTab] = useState<Tab>('sheet')
  const c = party.characters.find((x) => x.id === who)
  if (!c) return null
  const concentrating = c.effects.map((id) => party.effects.find((e) => e.id === id)).filter((e) => e?.concentration)
  return (
    <aside className="fixed inset-y-0 right-0 z-40 flex w-full max-w-2xl flex-col border-l-4 border-[var(--gold)] bg-[var(--ink)]" aria-label={`${c.name}'s sheet`}>
      <div className="flex flex-wrap items-center gap-2 border-b-2 border-[var(--border)] px-4 py-3">
        {party.characters.length > 1 ? (
          party.characters.map((x) => (
            <button
              key={x.id}
              type="button"
              onClick={() => onWho(x.id)}
              aria-pressed={x.id === who}
              className={`pixel-font border-2 px-2 py-1 text-[10px] ${x.id === who ? 'border-[var(--gold)] text-[var(--gold)]' : 'border-[var(--border)] text-[var(--dim)] hover:text-[var(--parchment)]'}`}
            >
              {x.name}
            </button>
          ))
        ) : (
          <h2 className="pixel-font text-[10px] text-[var(--gold)]">{c.name}</h2>
        )}
        <button type="button" onClick={onClose} className="pixel-font ml-auto text-[10px] text-[var(--dim)] hover:text-[var(--parchment)]">
          Close ✕
        </button>
      </div>
      <div role="tablist" className="flex border-b-2 border-[var(--border)]">
        {(
          [
            ['sheet', 'Character'],
            ['items', 'Inventory'],
            ['spells', 'Spells'],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className={`pixel-font flex-1 px-2 py-2 text-[10px] ${tab === id ? 'border-b-4 border-[var(--gold)] text-[var(--gold)]' : 'text-[var(--dim)] hover:text-[var(--parchment)]'}`}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {tab === 'sheet' && <SheetTab c={c} />}
        {tab === 'items' && <Inventory c={c} />}
        {tab === 'spells' && <Spells c={c} concentration={concentrating.map((e) => e?.label).join(', ')} />}
      </div>
    </aside>
  )
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center border-2 border-[var(--border)] bg-[var(--panel)] px-3 py-1">
      <span className="text-[11px] tracking-widest text-[var(--dim)] uppercase">{label}</span>
      <span className="pixel-font text-sm tabular-nums">{value}</span>
    </div>
  )
}

function SheetTab({ c }: { c: PartyChar }) {
  return (
    <div className="flex flex-col gap-4">
      <p className="text-lg">
        {c.race} {c.class} · level {c.level}
        {c.background ? ` · ${c.background}` : ''}
      </p>
      <div className="flex flex-wrap gap-2">
        <Stat label="Armor" value={c.armor_class} />
        <Stat label="HP" value={`${c.hp.current}/${c.hp.max}`} />
        <Stat label="Speed" value={`${c.speed} ft`} />
        <Stat label="Initiative" value={signed(c.initiative)} />
        <Stat label="Proficiency" value={signed(c.prof)} />
      </div>
      {c.death_saves && (c.death_saves.successes > 0 || c.death_saves.failures > 0) && (
        <p className="text-[var(--bad)]">
          Death saves: {c.death_saves.successes} successes, {c.death_saves.failures} failures
        </p>
      )}

      <section>
        <h3 className="pixel-font mb-2 text-[10px] text-[var(--gold)]">Abilities</h3>
        <ul className="grid grid-cols-3 gap-2 sm:grid-cols-6">
          {Object.entries(c.abilities).map(([name, a]) => (
            <li key={name} className="flex flex-col items-center border-2 border-[var(--border)] bg-[var(--panel)] py-2" title={`${titleCase(name)}: saving throw ${signed(a.save)}${a.save_prof ? ' (proficient)' : ''}`}>
              <span className="text-[11px] tracking-widest text-[var(--dim)] uppercase">{name.slice(0, 3)}</span>
              <span className="pixel-font text-lg">{signed(a.mod)}</span>
              <span className="text-sm text-[var(--dim)]">{a.score}</span>
              <span className="mt-1 text-xs" style={{ color: a.save_prof ? 'var(--gold)' : 'var(--dim)' }}>
                Save {signed(a.save)}
                {a.save_prof ? ' ●' : ''}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h3 className="pixel-font mb-2 text-[10px] text-[var(--gold)]">Skills</h3>
        <ul className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
          {c.skills.map((s) => (
            <li key={s.name} className="flex items-center gap-2 border-b border-[var(--border)] py-0.5">
              <span title={PROF_TEXT[s.prof]} style={{ color: s.prof ? 'var(--gold)' : 'var(--dim)' }} aria-label={PROF_TEXT[s.prof]}>
                {PROF_MARK[s.prof]}
              </span>
              <span className="flex-1">{s.name}</span>
              <span className="text-xs text-[var(--dim)]">{s.ability}</span>
              <span className="pixel-font w-8 text-right text-xs tabular-nums">{signed(s.bonus)}</span>
            </li>
          ))}
        </ul>
      </section>

      {c.weapons.length > 0 && (
        <section>
          <h3 className="pixel-font mb-2 text-[10px] text-[var(--gold)]">Weapons</h3>
          <ul className="flex flex-col gap-1">
            {c.weapons.map((w) => (
              <li key={w.name} className="flex items-baseline gap-2">
                <span className="flex-1">{w.name}</span>
                <span className="pixel-font text-xs">{w.attack_bonus !== undefined ? signed(w.attack_bonus) : ''}</span>
                <span className="text-[var(--dim)]">
                  {w.damage} {w.damage_type}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {c.features.length > 0 && (
        <section>
          <h3 className="pixel-font mb-2 text-[10px] text-[var(--gold)]">Features</h3>
          <ul className="flex flex-col gap-1">
            {c.features.map((f) => (
              <li key={f.name}>
                <details>
                  <summary className="cursor-pointer">{f.name}</summary>
                  <p className="pl-4 text-sm text-[var(--dim)]">{f.description}</p>
                </details>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

function ItemCell({ item, picked, onPick }: { item: Item; picked: boolean; onPick: () => void }) {
  const color = item.rarity ? RARITY[item.rarity] : 'var(--border)'
  return (
    <button
      type="button"
      onClick={onPick}
      aria-pressed={picked}
      className={`relative flex h-14 w-28 items-center justify-center border-2 bg-[var(--panel)] px-1 text-center text-sm leading-tight ${picked ? 'outline-2 outline-[var(--gold)]' : ''}`}
      style={{ borderColor: color, color: item.rarity ? color : 'var(--parchment)' }}
    >
      <span className="line-clamp-2">{item.name}</span>
      {item.quantity > 1 && <span className="absolute right-1 bottom-0 text-xs text-[var(--parchment)] tabular-nums">×{item.quantity}</span>}
    </button>
  )
}

/** Gold and the weight carried, equipped gear, then the backpack as a grid of item cells. */
function Inventory({ c }: { c: PartyChar }) {
  const [picked, setPicked] = useState<string | null>(null)
  const gold = c.inventory.find((i) => i.name === 'Gold Pieces')?.quantity ?? 0
  const items = c.inventory.filter((i) => i.name !== 'Gold Pieces')
  const weight = items.reduce((n, i) => n + i.weight * i.quantity, 0)
  const equipped = items.filter((i) => i.equipped)
  const pack = items.filter((i) => !i.equipped)
  const item = items.find((i) => i.name === picked)
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        <Stat label="Gold" value={gold} />
        <Stat label="Weight" value={`${Math.round(weight)} / ${c.capacity} lb`} />
        <Stat label="Armor" value={c.armor?.name ?? 'None'} />
      </div>
      {[
        ['Equipped', equipped],
        ['Backpack', pack],
      ].map(([title, list]) => (
        <section key={title as string}>
          <h3 className="pixel-font mb-2 text-[10px] text-[var(--gold)]">{title as string}</h3>
          {(list as Item[]).length ? (
            <div className="flex flex-wrap gap-1">
              {(list as Item[]).map((i) => (
                <ItemCell key={i.name} item={i} picked={picked === i.name} onPick={() => setPicked(picked === i.name ? null : i.name)} />
              ))}
            </div>
          ) : (
            <p className="text-[var(--dim)]">Nothing.</p>
          )}
        </section>
      ))}
      <section className="min-h-24 border-2 border-[var(--border)] bg-[var(--panel)] p-3" aria-live="polite">
        {item ? (
          <>
            <h3 className="text-lg" style={{ color: item.rarity ? RARITY[item.rarity] : undefined }}>
              {item.name}
              {item.quantity > 1 ? ` ×${item.quantity}` : ''}
            </h3>
            <p className="text-sm text-[var(--dim)]">
              {[item.rarity, item.equipped ? 'equipped' : null, item.weight ? `${item.weight * item.quantity} lb` : null].filter(Boolean).join(' · ')}
            </p>
            {item.description && <p className="mt-1">{item.description}</p>}
          </>
        ) : (
          <p className="text-[var(--dim)]">Pick an item to read about it.</p>
        )}
      </section>
    </div>
  )
}

interface Spell {
  index: string
  name: string
  level: number
  school: string
  casting_time: string
  range: string
  duration: string
  concentration: boolean
  ritual: boolean
  components: string[]
  desc: string
  higher_level: string
  damage?: string
  save?: string
}

const spellUrl = (index: string) => `/api/spell/${encodeURIComponent(index)}`

function SpellChip({ index, picked, onPick }: { index: string; picked: boolean; onPick: () => void }) {
  return (
    <button
      type="button"
      onClick={onPick}
      aria-pressed={picked}
      className={`border-2 px-2 py-1 text-left ${picked ? 'border-[var(--gold)] text-[var(--gold)]' : 'border-[var(--slot)]'}`}
    >
      {titleCase(index.replace(/'/g, ''))}
    </button>
  )
}

function SpellCard({ index }: { index: string }) {
  const spell = useJson<Spell>(spellUrl(index))
  if (spell === undefined) return <p className="text-[var(--dim)]">Reading the spellbook…</p>
  if (spell === null) return <p className="text-[var(--dim)]">{titleCase(index)}: no details (the rules library is offline).</p>
  return (
    <div className="flex flex-col gap-1">
      <h3 className="text-lg text-[var(--gold)]">{spell.name}</h3>
      <p className="text-sm text-[var(--dim)]">
        {spell.level === 0 ? 'Cantrip' : `Level ${spell.level}`} · {spell.school}
        {spell.concentration ? ' · concentration' : ''}
        {spell.ritual ? ' · ritual' : ''}
      </p>
      <p className="text-sm">
        {spell.casting_time} · {spell.range} · {spell.duration} · {spell.components?.join(', ')}
        {spell.damage ? ` · ${spell.damage} damage` : ''}
        {spell.save ? ` · ${spell.save} save` : ''}
      </p>
      <p>{spell.desc}</p>
      {spell.higher_level && <p className="text-sm text-[var(--dim)]">At higher levels: {spell.higher_level}</p>}
    </div>
  )
}

function Spells({ c, concentration }: { c: PartyChar; concentration?: string }) {
  const [picked, setPicked] = useState<string | null>(null)
  const knownLevels = useJson<Record<string, number>>('/api/spells')
  if (!c.spell) return <p className="text-[var(--dim)]">{c.name} casts no spells.</p>
  // Group by level when the rules library answered; otherwise one list (under "Cantrips" if no level is known).
  const byLevel: Record<number, string[]> = {}
  for (const s of c.spell.known) (byLevel[knownLevels?.[s.replace(/'/g, '')] ?? 0] ??= []).push(s)
  const levels = Object.keys(byLevel).map(Number).sort((a, b) => a - b)
  const grouped = Boolean(knownLevels && Object.keys(knownLevels).length)
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        {c.spell.ability && <Stat label="Ability" value={c.spell.ability.slice(0, 3).toUpperCase()} />}
        {c.spell.dc !== undefined && <Stat label="Save DC" value={c.spell.dc} />}
        {c.spell.attack !== undefined && <Stat label="Attack" value={signed(c.spell.attack)} />}
        {concentration && <Stat label="Concentrating" value={concentration} />}
      </div>
      <section>
        <h3 className="pixel-font mb-2 text-[10px] text-[var(--gold)]">Slots</h3>
        <SlotPips slots={c.spell.slots} />
        <p className="mt-1 text-xs text-[var(--dim)]">
          {Object.keys(c.spell.slots)
            .sort()
            .map((l) => `${ROMAN[Number(l)]}: ${c.spell!.slots[l].remaining}/${c.spell!.slots[l].max}`)
            .join('   ')}
        </p>
      </section>
      {c.spell.known.length === 0 && <p className="text-[var(--dim)]">No spells known yet.</p>}
      {levels.map((l) => (
        <section key={l}>
          <h3 className="pixel-font mb-2 text-[10px] text-[var(--gold)]">{!grouped ? 'Spells' : l === 0 ? 'Cantrips' : `Level ${ROMAN[l]}`}</h3>
          <div className="flex flex-wrap gap-1">
            {byLevel[l].map((s) => (
              <SpellChip key={s} index={s} picked={picked === s} onPick={() => setPicked(picked === s ? null : s)} />
            ))}
          </div>
        </section>
      ))}
      <section className="min-h-24 border-2 border-[var(--border)] bg-[var(--panel)] p-3" aria-live="polite">
        {picked ? <SpellCard index={picked} /> : <p className="text-[var(--dim)]">Pick a spell to read about it.</p>}
      </section>
    </div>
  )
}
