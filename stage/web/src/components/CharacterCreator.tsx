import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/8bit/button'
import { Input } from '@/components/ui/8bit/input'
import { postJson, titleCase, useJson } from '@/lib/stage'

interface Ref {
  index: string
  name: string
}
interface Race extends Ref {
  speed: number
  ability_bonuses: Record<string, number>
  bonus_choice: { count: number; options: string[] } | null
  subraces: (Ref & { ability_bonuses: Record<string, number> })[]
  look_race: string
}
interface Spellcasting {
  ability: string
  cantrips: number
  spells: number
  cantrip_options: Ref[]
  spell_options: Ref[]
}
interface Cls extends Ref {
  hit_die: number
  saves: string[]
  skill_count: number
  skill_options: string[]
  spellcasting: Spellcasting | null
  equipment: {
    fixed: (Ref & { quantity: number })[]
    choices: { label: string; options: Ref[] }[]
  }
}
interface Background extends Ref {
  skills: string[]
}
interface Options {
  races: Race[]
  classes: Cls[]
  backgrounds: Background[]
  skills: string[]
  abilities: string[]
  look: {
    bodies: string[]
    eyes: string[]
    races: Record<string, { skins: string[]; default_skin: string }>
    hair: { id: string; name: string }[]
    hair_colors: string[]
  }
}

type Mode = 'standard' | 'buy' | 'roll'

const STANDARD = [15, 14, 13, 12, 10, 8]
const COST: Record<number, number> = { 8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9 }
const ALIGNMENTS = [
  'Lawful Good', 'Neutral Good', 'Chaotic Good',
  'Lawful Neutral', 'True Neutral', 'Chaotic Neutral',
  'Lawful Evil', 'Neutral Evil', 'Chaotic Evil',
]
const STORY: [keyof Form, string][] = [
  ['traits', 'Personality traits'],
  ['ideals', 'Ideals'],
  ['bonds', 'Bonds'],
  ['flaws', 'Flaws'],
  ['backstory', 'Backstory'],
  ['past', 'What people or places from your past do you want to see again?'],
  ['problem', 'What unfinished problem does your character have?'],
]

interface Form {
  name: string
  alignment: string
  race: string
  subrace: string
  bonus: string[]
  cls: string
  bg: string
  customName: string
  customSkills: string[]
  mode: Mode
  pool: number[]
  slot: (number | null)[]
  buy: number[]
  skills: string[]
  cantrips: string[]
  spells: string[]
  gear: string[]
  lookRace: string
  body: string
  skin: string
  eyes: string
  hair: string
  color: string
  traits: string
  ideals: string
  bonds: string
  flaws: string
  backstory: string
  past: string
  problem: string
}

const blank: Form = {
  name: '', alignment: 'Neutral Good', race: '', subrace: '', bonus: [], cls: '', bg: '', customName: '', customSkills: [],
  mode: 'standard', pool: STANDARD, slot: Array(6).fill(null), buy: Array(6).fill(8),
  skills: [], cantrips: [], spells: [], gear: [], lookRace: '', body: '', skin: '', eyes: '', hair: '', color: '',
  traits: '', ideals: '', bonds: '', flaws: '', backstory: '', past: '', problem: '',
}

const field = 'w-full border-4 border-[var(--border)] bg-[var(--ink)] p-2 text-lg text-[var(--parchment)] focus:border-[var(--gold)] focus:outline-none'

const toggle = (list: string[], item: string, max = Infinity) =>
  list.includes(item) ? list.filter((x) => x !== item) : list.length < max ? [...list, item] : list

const mod = (score: number) => Math.floor((score - 10) / 2)
const signed = (n: number) => (n >= 0 ? `+${n}` : String(n))
const pick = (value: string, list: string[], fallback = '') => (list.includes(value) ? value : (list[0] ?? fallback))

function roll4d6(): number {
  const d = Array.from({ length: 4 }, () => 1 + Math.floor(Math.random() * 6)).sort((a, b) => a - b)
  return d[1] + d[2] + d[3]
}

function Pick({ on, onClick, disabled, children }: { on: boolean; onClick: () => void; disabled?: boolean; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      disabled={disabled}
      onClick={onClick}
      className={`border-4 px-3 py-1 text-lg disabled:opacity-40 ${on ? 'border-[var(--gold)] bg-[var(--gold)] text-[var(--ink)]' : 'border-[var(--border)] hover:border-[var(--parchment)]'}`}
    >
      {children}
    </button>
  )
}

function Group({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-lg">
        {label} {hint && <span className="text-sm text-[var(--dim)]">{hint}</span>}
      </legend>
      <div className="flex flex-wrap gap-2">{children}</div>
    </fieldset>
  )
}

function Select({ id, label, value, onChange, children }: { id: string; label: string; value: string; onChange: (v: string) => void; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-lg">
        {label}
      </label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)} className={field}>
        {children}
      </select>
    </div>
  )
}

export function CharacterCreator({ dmStatus, activity }: { dmStatus: string; activity?: string }) {
  const [options, setOptions] = useState<Options | null>(null)
  const [loadError, setLoadError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const party = useJson<{ characters: unknown[] }>('/api/party')
  const hadParty = Boolean(party?.characters.length)

  const [player, setPlayer] = useState('')
  const [f, setF] = useState<Form>(blank)
  const [step, setStep] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [made, setMade] = useState<string[]>([])
  const [madeAny, setMadeAny] = useState(false)

  const set = (p: Partial<Form>) => setF((s) => ({ ...s, ...p }))

  useEffect(() => {
    let live = true
    fetch('/api/creation/options')
      .then(async (r) => {
        const d = await r.json()
        if (!r.ok) throw new Error(d.error || 'The rulebooks could not be read.')
        return d as Options
      })
      .then((d) => live && setOptions(d))
      .catch((e) => live && setLoadError(e.message))
    return () => {
      live = false
    }
  }, [attempt])

  const finish = async () => {
    setBusy(true)
    await postJson('/api/creation/done').catch(() => null)
    setBusy(false)
  }

  const banner =
    dmStatus === 'busy' || dmStatus === 'starting'
      ? activity
        ? `The DM is building the world — ${activity}…`
        : 'The DM is building the world while you make your character…'
      : dmStatus === 'idle'
        ? 'The world is ready. Take your time.'
        : ''

  const shell = (body: React.ReactNode) => (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto border-4 border-[var(--border)] bg-[var(--panel)] p-4">
      {banner && <p className={`pixel-font truncate text-[10px] ${dmStatus === 'idle' ? 'text-emerald-400' : 'animate-pulse text-[var(--ember)]'}`}>{banner}</p>}
      {body}
    </div>
  )

  if (loadError) {
    return shell(
      <div className="flex flex-col items-start gap-3">
        <p role="alert" className="text-lg text-red-400">{loadError}</p>
        <Button onClick={() => {
            setLoadError('')
            setAttempt((n) => n + 1)
          }} className="text-[10px]">
          Retry
        </Button>
      </div>,
    )
  }
  if (!options) return shell(<p className="pixel-font animate-pulse text-xs text-[var(--dim)]">Reading the rulebooks…</p>)

  const race = options.races.find((r) => r.index === f.race)
  const sub = race?.subraces.find((s) => s.index === f.subrace)
  const cls = options.classes.find((c) => c.index === f.cls)
  const sc = cls?.spellcasting ?? null
  const bg = options.backgrounds.find((b) => b.index === f.bg)
  const bgSkills = f.bg === 'custom' ? f.customSkills : (bg?.skills ?? [])
  const abilities = options.abilities
  const prepared = Boolean(sc && sc.spells === 0)

  const base = f.mode === 'buy' ? f.buy : f.slot.map((i) => (i === null ? null : f.pool[i]))
  const bonus = (a: string) => (race?.ability_bonuses[a] ?? 0) + (sub?.ability_bonuses[a] ?? 0) + (f.bonus.includes(a) ? 1 : 0)
  const final = abilities.map((a, i) => (base[i] ?? 0) + bonus(a))
  const spent = f.buy.reduce((n, v) => n + COST[v], 0)
  const maxPrepared = sc ? Math.max(1, mod(final[abilities.indexOf(sc.ability)] ?? 10) + 1) : 0

  const look = options.look
  const lookRace = look.races[f.lookRace] ? f.lookRace : look.races[race?.look_race ?? ''] ? (race?.look_race ?? '') : Object.keys(look.races)[0]
  const skins = look.races[lookRace]?.skins ?? []
  const lk = {
    race: lookRace,
    body: pick(f.body, look.bodies),
    skin: pick(f.skin, skins, look.races[lookRace]?.default_skin),
    eyes: pick(f.eyes, look.eyes),
    hair: pick(f.hair, look.hair.map((h) => h.id)),
    color: pick(f.color, look.hair_colors),
  }
  const portrait = `/asset/look.png?${new URLSearchParams({ race: lk.race, body: lk.body, skin: lk.skin, eyes: lk.eyes, hair: `${lk.hair}:${lk.color}`, class: f.cls })}`

  const steps: { key: string; label: string; ok: boolean }[] = [
    { key: 'who', label: 'Who', ok: Boolean(player.trim() && f.name.trim() && f.alignment) },
    {
      key: 'race', label: 'Race',
      ok: Boolean(race && (race.subraces.length === 0 || sub) && f.bonus.length === (race.bonus_choice?.count ?? 0)),
    },
    { key: 'class', label: 'Class', ok: Boolean(cls) },
    { key: 'bg', label: 'Background', ok: f.bg === 'custom' ? Boolean(f.customName.trim()) && f.customSkills.length === 2 : Boolean(bg) },
    { key: 'abilities', label: 'Abilities', ok: f.mode === 'buy' ? spent <= 27 : base.every((v) => v !== null) },
    { key: 'skills', label: 'Skills', ok: f.skills.length === (cls?.skill_count ?? 0) },
    ...(sc
      ? [{ key: 'spells', label: 'Spells', ok: f.cantrips.length === sc.cantrips && (prepared ? f.spells.length <= maxPrepared : f.spells.length === sc.spells) }]
      : []),
    { key: 'gear', label: 'Gear', ok: (cls?.equipment.choices ?? []).every((_, i) => f.gear[i]) },
    { key: 'look', label: 'Look', ok: Boolean(lk.body && lk.eyes && lk.hair) },
    { key: 'story', label: 'Story', ok: true },
    { key: 'review', label: 'Review', ok: true },
  ]
  const cur = steps[step]

  const create = async () => {
    if (!race || !cls) return
    setBusy(true)
    setError('')
    const body = {
      player_name: player.trim(),
      name: f.name.trim(),
      race: race.index,
      subrace: f.subrace,
      class: cls.index,
      background: f.bg === 'custom' ? f.customName.trim() : f.bg,
      background_skills: f.bg === 'custom' ? f.customSkills : [],
      scores: base,
      assign: ['str', 'dex', 'con', 'int', 'wis', 'cha'],
      bonus_abilities: f.bonus,
      skills: f.skills,
      cantrips: f.cantrips,
      spells: f.spells,
      equipment: [
        ...cls.equipment.fixed.flatMap((i) => Array<string>(i.quantity || 1).fill(i.index)),
        ...f.gear,
      ],
      alignment: f.alignment,
      personality_traits: f.traits,
      ideals: f.ideals,
      bonds: f.bonds,
      flaws: f.flaws,
      backstory: f.backstory,
      hooks: { past: f.past, problem: f.problem },
      look: { race: lk.race, body: lk.body, skin: lk.skin, eyes: lk.eyes, hair: `${lk.hair}:${lk.color}` },
    }
    try {
      const d = await (await postJson('/api/creation/character', body)).json()
      if (d.error) setError(String(d.error))
      else {
        setMade(d.lines ?? [])
        setMadeAny(true)
      }
    } catch {
      setError('The table server did not answer.')
    }
    setBusy(false)
  }

  const nav = (
    <div className="mt-auto flex flex-wrap items-center gap-3 pt-2">
      <Button variant="outline" disabled={step === 0 || busy} onClick={() => setStep(step - 1)} className="text-[10px]">
        Back
      </Button>
      {cur.key === 'review' ? (
        <Button disabled={busy} onClick={create} className="text-[10px]">
          {busy ? 'Creating…' : 'Create'}
        </Button>
      ) : (
        <Button disabled={!cur.ok} onClick={() => setStep(step + 1)} className="text-[10px]">
          Next
        </Button>
      )}
      {!madeAny && hadParty && (
        <Button variant="outline" disabled={busy} onClick={finish} className="ml-auto text-[10px]">
          Cancel
        </Button>
      )}
    </div>
  )

  if (made.length > 0) {
    return shell(
      <div className="flex flex-col gap-4">
        <h2 className="pixel-font text-xs text-[var(--gold)]">Character created</h2>
        <ul className="text-lg">
          {made.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
        <div className="flex flex-wrap gap-3">
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => {
              setF(blank)
              setStep(0)
              setMade([])
            }}
            className="text-[10px]"
          >
            Make another character
          </Button>
          <Button disabled={busy} onClick={finish} className="text-[10px]">
            {hadParty ? 'Join the party' : 'Begin adventure'}
          </Button>
        </div>
      </div>,
    )
  }

  const pickOptions = (list: Ref[], chosen: string[], key: 'cantrips' | 'spells', max: number) =>
    list.map((o) => (
      <Pick key={o.index} on={chosen.includes(o.index)} onClick={() => set({ [key]: toggle(chosen, o.index, max) })}>
        {o.name}
      </Pick>
    ))

  return shell(
    <>
      <h2 className="pixel-font text-xs text-[var(--gold)]">
        {step + 1}/{steps.length} · {cur.label}
      </h2>

      {cur.key === 'who' && (
        <div className="flex max-w-md flex-col gap-3">
          <label htmlFor="cc-player" className="text-lg">Player name</label>
          <Input id="cc-player" value={player} onChange={(e) => setPlayer(e.target.value)} font="normal" className="text-lg" />
          <label htmlFor="cc-name" className="text-lg">Character name</label>
          <Input id="cc-name" value={f.name} onChange={(e) => set({ name: e.target.value })} font="normal" className="text-lg" />
          <Select id="cc-align" label="Alignment" value={f.alignment} onChange={(v) => set({ alignment: v })}>
            {ALIGNMENTS.map((a) => <option key={a}>{a}</option>)}
          </Select>
        </div>
      )}

      {cur.key === 'race' && (
        <>
          <Group label="Race">
            {options.races.map((r) => (
              <Pick key={r.index} on={f.race === r.index} onClick={() => set({ race: r.index, subrace: '', bonus: [], lookRace: '', skin: '' })}>
                {r.name}
              </Pick>
            ))}
          </Group>
          {race && (
            <p className="text-lg text-[var(--dim)]">
              Speed {race.speed}. {Object.entries({ ...race.ability_bonuses, ...sub?.ability_bonuses }).map(([a, n]) => `${titleCase(a)} ${signed(n)}`).join(', ')}
            </p>
          )}
          {race && race.subraces.length > 0 && (
            <Group label="Subrace">
              {race.subraces.map((s) => (
                <Pick key={s.index} on={f.subrace === s.index} onClick={() => set({ subrace: s.index })}>
                  {s.name}
                </Pick>
              ))}
            </Group>
          )}
          {race?.bonus_choice && (
            <Group label={`Pick ${race.bonus_choice.count} abilities for +1`} hint={`${f.bonus.length}/${race.bonus_choice.count}`}>
              {race.bonus_choice.options.map((a) => (
                <Pick key={a} on={f.bonus.includes(a)} onClick={() => set({ bonus: toggle(f.bonus, a, race.bonus_choice!.count) })}>
                  {titleCase(a)}
                </Pick>
              ))}
            </Group>
          )}
        </>
      )}

      {cur.key === 'class' && (
        <>
          <Group label="Class">
            {options.classes.map((c) => (
              <Pick key={c.index} on={f.cls === c.index} onClick={() => set({ cls: c.index, skills: [], cantrips: [], spells: [], gear: [] })}>
                {c.name}
              </Pick>
            ))}
          </Group>
          {cls && (
            <p className="text-lg text-[var(--dim)]">
              Hit die d{cls.hit_die}. Saves: {cls.saves.map(titleCase).join(', ')}.{sc ? ` Casts with ${titleCase(sc.ability)}.` : ''}
            </p>
          )}
        </>
      )}

      {cur.key === 'bg' && (
        <>
          <Group label="Background">
            {options.backgrounds.map((b) => (
              <Pick key={b.index} on={f.bg === b.index} onClick={() => set({ bg: b.index, skills: [] })}>
                {b.name}
              </Pick>
            ))}
            <Pick on={f.bg === 'custom'} onClick={() => set({ bg: 'custom', skills: [] })}>
              Custom background
            </Pick>
          </Group>
          {bg && f.bg !== 'custom' && <p className="text-lg text-[var(--dim)]">Skills: {bg.skills.map(titleCase).join(', ')}</p>}
          {f.bg === 'custom' && (
            <>
              <label htmlFor="cc-bgname" className="text-lg">Background name</label>
              <Input id="cc-bgname" value={f.customName} onChange={(e) => set({ customName: e.target.value })} font="normal" className="max-w-md text-lg" />
              <Group label="Two skills" hint={`${f.customSkills.length}/2`}>
                {options.skills.map((s) => (
                  <Pick key={s} on={f.customSkills.includes(s)} onClick={() => set({ customSkills: toggle(f.customSkills, s, 2), skills: [] })}>
                    {titleCase(s)}
                  </Pick>
                ))}
              </Group>
            </>
          )}
        </>
      )}

      {cur.key === 'abilities' && (
        <>
          <Group label="Method">
            {([['standard', 'Standard array'], ['buy', 'Point buy'], ['roll', 'Roll 4d6']] as [Mode, string][]).map(([m, label]) => (
              <Pick
                key={m}
                on={f.mode === m}
                onClick={() => set({ mode: m, slot: Array(6).fill(null), pool: m === 'roll' ? [] : STANDARD, buy: Array(6).fill(8) })}
              >
                {label}
              </Pick>
            ))}
          </Group>
          {f.mode === 'buy' && <p className="text-lg">Points left: {27 - spent}</p>}
          {f.mode === 'roll' && (
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="outline" onClick={() => set({ pool: Array.from({ length: 6 }, roll4d6).sort((a, b) => b - a), slot: Array(6).fill(null) })} className="text-[10px]">
                {f.pool.length ? 'Roll again' : 'Roll'}
              </Button>
              <span className="text-lg">{f.pool.join(', ')}</span>
            </div>
          )}
          <table className="max-w-xl text-left text-lg">
            <thead className="text-sm text-[var(--dim)]">
              <tr>
                <th>Ability</th>
                <th>Base</th>
                <th>Race</th>
                <th>Score</th>
                <th>Mod</th>
              </tr>
            </thead>
            <tbody>
              {abilities.map((a, i) => (
                <tr key={a}>
                  <th scope="row" className="font-normal">{titleCase(a)}</th>
                  <td>
                    {f.mode === 'buy' ? (
                      <span className="flex items-center gap-2">
                        <Button size="sm" variant="outline" aria-label={`Lower ${a}`} disabled={f.buy[i] <= 8} onClick={() => set({ buy: f.buy.map((v, j) => (j === i ? v - 1 : v)) })} className="px-2 text-[10px]">-</Button>
                        {f.buy[i]}
                        <Button size="sm" variant="outline" aria-label={`Raise ${a}`} disabled={f.buy[i] >= 15 || spent - COST[f.buy[i]] + COST[f.buy[i] + 1] > 27} onClick={() => set({ buy: f.buy.map((v, j) => (j === i ? v + 1 : v)) })} className="px-2 text-[10px]">+</Button>
                      </span>
                    ) : (
                      <select
                        aria-label={`${titleCase(a)} base score`}
                        value={f.slot[i] ?? ''}
                        onChange={(e) => set({ slot: f.slot.map((v, j) => (j === i ? (e.target.value === '' ? null : Number(e.target.value)) : v)) })}
                        className={`${field} !w-auto !p-1`}
                      >
                        <option value="">-</option>
                        {f.pool.map((v, p) => (f.slot.includes(p) && f.slot[i] !== p ? null : <option key={p} value={p}>{v}</option>))}
                      </select>
                    )}
                  </td>
                  <td className="text-[var(--dim)]">{bonus(a) ? signed(bonus(a)) : ''}</td>
                  <td>{base[i] === null ? '-' : final[i]}</td>
                  <td>{base[i] === null ? '' : signed(mod(final[i]))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {cur.key === 'skills' && cls && (
        <Group label="Class skills" hint={`${f.skills.length}/${cls.skill_count}`}>
          {cls.skill_options
            .filter((s) => !bgSkills.includes(s))
            .map((s) => (
              <Pick key={s} on={f.skills.includes(s)} onClick={() => set({ skills: toggle(f.skills, s, cls.skill_count) })}>
                {titleCase(s)}
              </Pick>
            ))}
        </Group>
      )}

      {cur.key === 'spells' && sc && (
        <>
          <Group label="Cantrips" hint={`${f.cantrips.length}/${sc.cantrips}`}>
            {pickOptions(sc.cantrip_options, f.cantrips, 'cantrips', sc.cantrips)}
          </Group>
          <Group label="Level 1 spells" hint={prepared ? `${f.spells.length}/up to ${maxPrepared}` : `${f.spells.length}/${sc.spells}`}>
            {pickOptions(sc.spell_options, f.spells, 'spells', prepared ? maxPrepared : sc.spells)}
          </Group>
          {prepared && <p className="text-lg text-[var(--dim)]">You prepare spells each day. Pick up to {maxPrepared} now (ability modifier + 1).</p>}
        </>
      )}

      {cur.key === 'gear' && cls && (
        <>
          <p className="text-lg">You start with: {cls.equipment.fixed.map((i) => (i.quantity > 1 ? `${i.name} ×${i.quantity}` : i.name)).join(', ') || 'nothing fixed'}.</p>
          {cls.equipment.choices.map((c, i) => (
            <Select key={i} id={`cc-gear-${i}`} label={c.label} value={f.gear[i] ?? ''} onChange={(v) => set({ gear: cls.equipment.choices.map((_, j) => (j === i ? v : (f.gear[j] ?? ''))) })}>
              <option value="">Choose…</option>
              {c.options.map((o) => <option key={o.index} value={o.index}>{o.name}</option>)}
            </Select>
          ))}
        </>
      )}

      {cur.key === 'look' && (
        <div className="flex flex-wrap items-start gap-6">
          <img src={portrait} alt="Portrait preview" className="pixelated size-40 border-4 border-[var(--border)] bg-black object-contain" onError={(e) => (e.currentTarget.style.visibility = 'hidden')} onLoad={(e) => (e.currentTarget.style.visibility = 'visible')} />
          <div className="grid min-w-0 flex-1 gap-3 sm:grid-cols-2">
            <Select id="cc-lrace" label="Look race" value={lk.race} onChange={(v) => set({ lookRace: v, skin: '' })}>
              {Object.keys(look.races).map((r) => <option key={r} value={r}>{titleCase(r)}</option>)}
            </Select>
            <Select id="cc-body" label="Body" value={lk.body} onChange={(v) => set({ body: v })}>
              {look.bodies.map((b) => <option key={b} value={b}>{titleCase(b)}</option>)}
            </Select>
            <Select id="cc-skin" label="Skin" value={lk.skin} onChange={(v) => set({ skin: v })}>
              {skins.map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}
            </Select>
            <Select id="cc-eyes" label="Eyes" value={lk.eyes} onChange={(v) => set({ eyes: v })}>
              {look.eyes.map((e) => <option key={e} value={e}>{titleCase(e)}</option>)}
            </Select>
            <Select id="cc-hair" label="Hair style" value={lk.hair} onChange={(v) => set({ hair: v })}>
              {look.hair.map((h) => <option key={h.id} value={h.id}>{h.name}</option>)}
            </Select>
            <Select id="cc-color" label="Hair color" value={lk.color} onChange={(v) => set({ color: v })}>
              {look.hair_colors.map((c) => <option key={c} value={c}>{titleCase(c)}</option>)}
            </Select>
          </div>
        </div>
      )}

      {cur.key === 'story' && (
        <div className="flex max-w-2xl flex-col gap-3">
          {STORY.map(([k, label]) => (
            <div key={k} className="flex flex-col gap-1">
              <label htmlFor={`cc-${k}`} className="text-lg">{label}</label>
              <textarea id={`cc-${k}`} rows={k === 'backstory' ? 4 : 2} value={f[k] as string} onChange={(e) => set({ [k]: e.target.value })} className={field} />
            </div>
          ))}
        </div>
      )}

      {cur.key === 'review' && race && cls && (
        <div className="flex flex-col gap-1 text-lg">
          <p>
            <span className="text-[var(--gold)]">{f.name}</span> ({player}) · {f.alignment}
          </p>
          <p>
            {race.name}{sub ? ` (${sub.name})` : ''} {cls.name} · {f.bg === 'custom' ? f.customName : bg?.name}
          </p>
          <p>{abilities.map((a, i) => `${a.slice(0, 3).toUpperCase()} ${final[i]} (${signed(mod(final[i]))})`).join(' · ')}</p>
          <p>Skills: {[...bgSkills, ...f.skills].map(titleCase).join(', ')}</p>
          {sc && <p>Spells: {[...f.cantrips, ...f.spells].map(titleCase).join(', ') || 'none yet'}</p>}
          <p>
            Gear: {[...cls.equipment.fixed.map((i) => i.name), ...f.gear.map((g) => cls.equipment.choices.flatMap((c) => c.options).find((o) => o.index === g)?.name ?? g)].join(', ')}
          </p>
          <p className="text-[var(--dim)]">
            Look: {titleCase(lk.race)}, {lk.body}, {lk.skin} skin, {lk.eyes} eyes, {lk.color.replace('_', ' ')} {look.hair.find((h) => h.id === lk.hair)?.name} hair
          </p>
          {error && <p role="alert" className="text-lg text-red-400">{error}</p>}
        </div>
      )}

      {nav}
    </>,
  )
}
