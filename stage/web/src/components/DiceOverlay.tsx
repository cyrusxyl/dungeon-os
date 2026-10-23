import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import { DiceTray, type TrayRow } from '@/components/DiceTray'
import { Die, DIE_MS } from '@/components/Die'
import { damageTone, diceFor, type Tone } from '@/lib/dice'
import { useDock } from '@/lib/dock'
import { HOLD_MS, timeScale, usePrefs } from '@/lib/prefs'
import type { Roll, RollDetail, RollEntry } from '@/lib/stage'

// The roll window plays like the one in Baldur's Gate 3: the dice tumble and land, advantage drops the lower die,
// then each tile adds to the total, one by one, and the result lands last.
// A click while the dice still roll skips to the landed dice.
const TUMBLE_MS = DIE_MS
const SETTLE_MS = 400
const TILE_MS = 280
// When more rolls wait (a round of attacks), each window gives way sooner.
const QUEUED_HOLD_MS = 1500

const OUTCOME_TEXT: Record<string, string> = {
  success: 'Success',
  fail: 'Failure',
  hit: 'Hit',
  miss: 'Miss',
  crit: 'Critical Hit',
  fumble: 'Critical Miss',
}
const OUTCOME_COLOR: Record<string, string> = {
  success: 'var(--good)',
  hit: 'var(--good)',
  crit: 'var(--gold)',
  fail: 'var(--bad)',
  miss: 'var(--bad)',
  fumble: 'var(--bad)',
}

/** What a window needs to host a `DiceTray`: has it landed (so the hold timer may start), and the handle a click on the window calls first. */
function useTray(has: boolean) {
  const [landed, setLanded] = useState(!has)
  const onLanded = useCallback(() => setLanded(true), [])
  const trayRef = useRef<(() => boolean) | null>(null)
  return { landed, onLanded, trayRef }
}

/** The most dice the tray throws. A roll with more shows as text. */
const MAX_DICE = 60

/** The tray rows for a roll's damage, or null when a row has no groups or a die the game cannot draw. */
function damageRows(damage: RollDetail['damage']): TrayRow[] | null {
  if (!damage?.length) return null
  const rows: TrayRow[] = []
  for (const d of damage) {
    if (!d.groups?.length) return null
    const dice: TrayRow['dice'] = []
    for (const g of d.groups) {
      const part = groupDice(g)
      if (!part) return null
      dice.push(...part)
    }
    rows.push({ label: d.type || 'damage', expr: d.expr, tone: damageTone(d.type), dice, total: d.total })
  }
  return rows.reduce((n, r) => n + r.dice.length, 0) <= MAX_DICE ? rows : null
}
/** The dice for one group like {die: "2d6", faces: [4, 5]}, or null for a die the game cannot draw. */
function groupDice(g: { die: string; faces: number[] }): TrayRow['dice'] | null {
  const m = /^(\d+)d(\d+)$/.exec(g.die)
  if (!m) return null
  const out: TrayRow['dice'] = []
  for (const face of g.faces) {
    const d = diceFor(Number(m[2]), face)
    if (!d.length) return null
    out.push(...d)
  }
  return out
}
/** A plain roll as one row. A roll with a d20 in it keeps the d20 look instead (see `PlainDie`): only the other dice are thrown. */
function plainRows(roll: Roll): TrayRow[] | null {
  const dice: TrayRow['dice'] = []
  for (const g of roll.dice) {
    const part = /d20( dropped)?$/.test(g.die) ? null : groupDice(g)
    if (!part) return null
    dice.push(...part)
  }
  return dice.length && dice.length <= MAX_DICE ? [{ label: 'Roll', expr: roll.expr, tone: 'plain', dice, total: roll.total }] : null
}

/**
 * Where the roll animation is. `settled`: the dice have landed. `shown`: how many of `count` tiles have landed.
 * `done`: everything is on screen. With `tm` 0 (no motion) it starts done. `tm` scales every wait. `skip` ends the tumble now.
 */
function useReveal(count: number, tm: number): { settled: boolean; shown: number; done: boolean; skip: () => void } {
  const [step, setStep] = useState(() => (tm === 0 ? count + 2 : 0))
  useEffect(() => {
    if (step >= count + 2) return
    const t = window.setTimeout(() => setStep(step + 1), (step === 0 ? TUMBLE_MS : step === 1 ? SETTLE_MS : TILE_MS) * tm)
    return () => window.clearTimeout(t)
  }, [step, count, tm])
  const skip = () => setStep((s) => Math.max(s, 1))
  return { settled: step >= 1, shown: Math.min(Math.max(step - 1, 0), count), done: step >= count + 2, skip }
}

const signed = (n: number) => (n >= 0 ? `+${n}` : `${n}`)

/** Plays each roll the stage has not shown yet, one after the other. */
export function DiceOverlay({ rolls }: { rolls: Roll[] }) {
  // Rolls already on record when the page loads are history, not news.
  const seen = useRef(rolls.at(-1)?.seq ?? 0)
  const [queue, setQueue] = useState<Roll[]>([])
  const prefs = usePrefs()
  const off = prefs.dice === 'off'

  useEffect(() => {
    const fresh = rolls.filter((r) => r.seq > seen.current)
    if (!fresh.length) return
    seen.current = fresh[fresh.length - 1].seq
    if (!off) setQueue((q) => [...q, ...fresh]) // Off: no window; the story log still has the roll
  }, [rolls, off])

  // Stable: every state snapshot renders this again, and a new function would restart the hold timer.
  const next = useCallback(() => setQueue((q) => q.slice(1)), [])
  const roll = queue[0]
  if (!roll || off) return null
  const queued = queue.length > 1
  const hold = queued ? QUEUED_HOLD_MS : HOLD_MS[prefs.hold]
  return roll.detail ? (
    <RollWindow key={roll.seq} detail={roll.detail} seq={roll.seq} hold={hold} queued={queued} onDone={next} />
  ) : (
    <PlainRoll key={roll.seq} roll={roll} hold={hold} queued={queued} onDone={next} />
  )
}

function useDismiss(done: boolean, hold: number, onDone: () => void) {
  useEffect(() => {
    if (!done || !Number.isFinite(hold)) return // `Until I click`: the player closes it
    const t = window.setTimeout(onDone, hold)
    return () => window.clearTimeout(t)
  }, [done, hold, onDone])
}

export function Tile({ label, value, sub, tone, shown, small }: { label: string; value: string; sub?: string; tone: 'plain' | 'bonus' | 'penalty'; shown: boolean; small?: boolean }) {
  const border = tone === 'bonus' ? 'border-[var(--gold)]' : tone === 'penalty' ? 'border-[var(--bad)]' : 'border-[var(--border)]'
  const color = tone === 'penalty' ? 'var(--bad)' : tone === 'bonus' ? 'var(--gold)' : 'var(--parchment)'
  if (small) {
    // One line: the strip under the board has little height.
    return (
      <div className={`flex items-center gap-1 border-2 bg-[var(--panel-2)] px-1.5 py-0.5 ${border} ${shown ? 'tile-in' : 'invisible'}`}>
        <span className="pixel-font text-[9px] tabular-nums" style={{ color }}>{value}</span>
        {sub && <span className="text-[11px] leading-none text-[var(--ember)]">{sub}</span>}
        <span className="text-xs leading-none text-[var(--dim)]">{label}</span>
      </div>
    )
  }
  return (
    <div className={`flex w-[4.75rem] flex-col items-center gap-1 border-2 bg-[var(--panel-2)] px-1 py-2 text-center ${border} ${shown ? 'tile-in' : 'invisible'}`}>
      <span className="pixel-font text-xs tabular-nums" style={{ color }}>
        {value}
      </span>
      {sub && <span className="text-[11px] leading-none text-[var(--ember)]">{sub}</span>}
      <span className="text-xs leading-tight text-[var(--dim)]">{label}</span>
    </div>
  )
}

function ModeBadge({ mode }: { mode: RollEntry['mode'] }) {
  if (mode === 'normal') return null
  const adv = mode === 'advantage'
  return (
    <span className="badge-pulse pixel-font text-[10px]" style={{ color: adv ? 'var(--good)' : 'var(--bad)' }}>
      {adv ? '▲ Advantage' : '▼ Disadvantage'}
    </span>
  )
}

export function Shell({ children, className = '', low = false }: { children: React.ReactNode; className?: string; low?: boolean }) {
  const dock = useDock()
  // In a fight the window sits in the strip under the board, so the board stays in view.
  if (dock) return createPortal(<div className="dice-pop h-full overflow-y-auto bg-[var(--panel)] p-2">{children}</div>, dock)
  return (
    <div className={`pointer-events-none fixed inset-0 z-40 flex items-start justify-center ${low ? 'pt-[56vh]' : 'pt-[8vh]'}`}>
      <div className={`dice-pop pointer-events-auto relative border-4 border-[var(--gold)] bg-[var(--panel)] px-5 py-4 ${className}`}>{children}</div>
    </div>
  )
}

/** The d20 and its total on the left, the damage tray on the right: a roll in the strip under the board of a fight. */
function StripRoll({ entry, title, subtitle, target, settled, shown, done, rate, rows, crit, seq, queued, onLanded, trayRef, damage }: {
  entry: RollEntry; title: string; subtitle?: string; target?: { label: string; value: number }; settled: boolean; shown: number; done: boolean; rate: number
  rows: TrayRow[] | null; crit: boolean; seq: number; queued: boolean; onLanded: () => void; trayRef: React.MutableRefObject<(() => boolean) | null>; damage: RollDetail['damage']
}) {
  const prefs = usePrefs()
  const kept = entry.d20[entry.kept]
  const tiles = [
    ...entry.mods.map((m) => ({ label: m.label, value: signed(m.value), sub: undefined, tone: 'plain' as const })),
    ...entry.bonus.map((b) => ({ label: b.label, value: signed(b.value), sub: `${b.die} → ${b.faces.join('+')}`, tone: (b.value < 0 ? 'penalty' : 'bonus') as 'penalty' | 'bonus' })),
  ]
  const running = prefs.tiles ? kept + tiles.slice(0, shown).reduce((n, t) => n + Number(t.value), 0) : entry.total
  const two = entry.d20.length > 1
  const flair = done && kept === 20 ? 'burst' : done && kept === 1 ? 'shake' : ''
  const tone = (face: number, counts: boolean): Tone => (!counts ? 'plain' : face === 20 ? 'gold' : face === 1 ? 'red' : 'plain')
  return (
    <div className="flex min-h-full items-stretch gap-2">
      <div className={`relative flex w-28 shrink-0 flex-col items-center justify-center gap-1 border-r-2 border-[var(--border)] pr-2 ${flair}`}>
        <span className="max-w-full truncate text-xs text-[var(--dim)]">{entry.name}</span>
        <div className="flex items-end gap-1">
          {entry.d20.map((face, i) => {
            const counts = i === entry.kept
            const glow = entry.mode === 'advantage' ? 'var(--good)' : entry.mode === 'disadvantage' ? 'var(--bad)' : 'var(--gold)'
            return <Die key={i} face={face} tone={tone(face, counts)} settled={settled} size={two ? 44 : 60} className={settled && two ? (counts ? 'die-kept' : 'die-dropped') : ''} glow={glow} rate={rate} />
          })}
        </div>
        <ModeBadge mode={entry.mode} />
        <div className="pixel-font text-lg tabular-nums" style={{ color: done ? 'var(--parchment)' : 'var(--dim)' }}>
          {settled ? running : '?'}
        </div>
        {target && <span className="text-xs text-[var(--dim)]">vs {target.label === 'Armor Class' ? 'AC' : target.label} {target.value}</span>}
        {done && entry.outcome && (
          <span className="result-in pixel-font text-[9px]" style={{ color: OUTCOME_COLOR[entry.outcome] }}>
            {OUTCOME_TEXT[entry.outcome]}
          </span>
        )}
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex items-baseline gap-2 truncate text-sm">
          <span className="pixel-font shrink-0 text-[10px] text-[var(--parchment)]">{title}</span>
          {subtitle && <span className="truncate text-[var(--ember)]">{subtitle}</span>}
        </div>
        {prefs.tiles && tiles.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {tiles.map((t, i) => (
              <Tile key={i} label={t.label} value={t.value} sub={t.sub} tone={t.tone} shown={i < shown} small />
            ))}
          </div>
        )}
        {done && rows && <DiceTray rows={rows} crit={crit} seed={seq} queued={queued} onSettled={onLanded} skipRef={trayRef} compact />}
        {done && damage && !rows && (
          <ul className="result-in flex flex-col text-base">
            {damage.map((d, i) => (
              <li key={i}>
                <span className="pixel-font text-sm text-[var(--ember)]">{d.total}</span> <span className="capitalize">{d.type || 'damage'}</span>{' '}
                <span className="text-sm text-[var(--dim)]">{d.expr} [{d.faces.join(', ')}]</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

/** The roll window: a check, a saving throw, an attack or a death save, with every tile that makes the total. */
function RollWindow({ detail, seq, hold, queued, onDone }: { detail: RollDetail; seq: number; hold: number; queued: boolean; onDone: () => void }) {
  const prefs = usePrefs()
  const tm = timeScale(prefs)
  const group = detail.rolls.length > 1
  const tileCount = group ? detail.rolls.length : prefs.tiles ? detail.rolls[0].mods.length + detail.rolls[0].bonus.length : 0
  const { settled, shown, done, skip } = useReveal(tileCount, tm)
  // The damage tray (when the roll has damage groups the game can draw). Until it has landed the window stays open.
  const rows = useMemo(() => (prefs.dice === 'tray' ? damageRows(detail.damage) : null), [prefs.dice, detail.damage])
  const { landed, onLanded, trayRef } = useTray(Boolean(rows))
  const rate = tm ? 1 / tm : 1
  useDismiss(done && landed, hold, onDone)

  const summary = detail.rolls.map((r) => `${r.name} ${r.total}${r.outcome ? ` ${OUTCOME_TEXT[r.outcome]}` : ''}`).join(', ')
  const damageSummary = detail.damage?.map((d) => `${d.total} ${d.type || 'damage'}`).join(', ')
  const crit = detail.rolls[0]?.outcome === 'crit'
  const dock = useDock()
  const onClick = () => {
    if (trayRef.current?.()) return // a click throws the dice, or lands them
    if (settled) onDone()
    else skip()
  }
  if (dock && !group) {
    return (
      <Shell>
        <div role="status" aria-live="polite" onClick={onClick} className="cursor-pointer">
          <span className="sr-only">{`${detail.title}. ${summary}${damageSummary ? `. Damage: ${damageSummary}` : ''}`}</span>
          <StripRoll entry={detail.rolls[0]} title={detail.title} subtitle={detail.subtitle} target={detail.target} settled={settled} shown={shown} done={done} rate={rate} rows={rows} crit={crit} seq={seq} queued={queued} onLanded={onLanded} trayRef={trayRef} damage={detail.damage} />
        </div>
      </Shell>
    )
  }
  return (
    <Shell className={group || rows ? 'w-[28rem] max-w-[94vw]' : 'w-[22rem] max-w-[94vw]'}>
      <div
        role="status"
        aria-live="polite"
        onClick={onClick}
        className="flex cursor-pointer flex-col items-center gap-2"
      >
        <span className="sr-only">{`${detail.title}. ${summary}${damageSummary ? `. Damage: ${damageSummary}` : ''}`}</span>
        {!group && <span className="text-sm text-[var(--dim)]">{detail.rolls[0].name}</span>}
        <h2 className="pixel-font text-sm text-[var(--parchment)]">{detail.title}</h2>
        {detail.subtitle && <p className="text-[var(--ember)]">{detail.subtitle}</p>}
        {detail.target && (
          <div className="flex flex-col items-center border-y-2 border-[var(--border)] px-8 py-1">
            <span className="text-[11px] tracking-widest text-[var(--dim)] uppercase">{detail.target.label}</span>
            <span className="pixel-font text-xl tabular-nums">{detail.target.value}</span>
          </div>
        )}
        {group ? (
          <RollRows rolls={detail.rolls} settled={settled} shown={shown} showTiles={prefs.tiles} rate={rate} />
        ) : (
          <SingleRoll entry={detail.rolls[0]} settled={settled} shown={shown} done={done} showTiles={prefs.tiles} rate={rate} />
        )}
        {done && !group && detail.rolls[0].outcome && <Result outcome={detail.rolls[0].outcome} d20={detail.rolls[0].d20[detail.rolls[0].kept]} />}
        {done && rows && (
          <DiceTray rows={rows} crit={crit} seed={seq} queued={queued} onSettled={onLanded} skipRef={trayRef} />
        )}
        {done && detail.damage && !rows && (
          <ul className="result-in flex flex-col items-center text-lg">
            {detail.damage.map((d, i) => (
              <li key={i}>
                <span className="pixel-font text-sm text-[var(--ember)]">{d.total}</span> <span className="capitalize">{d.type || 'damage'}</span>{' '}
                <span className="text-sm text-[var(--dim)]">
                  {d.expr} [{d.faces.join(', ')}]
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Shell>
  )
}

function Result({ outcome, d20 }: { outcome: NonNullable<RollEntry['outcome']>; d20: number }) {
  return (
    <div className="result-in flex flex-col items-center gap-1">
      <span className="pixel-font text-base" style={{ color: OUTCOME_COLOR[outcome] }}>
        {OUTCOME_TEXT[outcome]}
      </span>
      {d20 === 20 && outcome !== 'crit' && <span className="text-sm text-[var(--gold)]">Natural 20</span>}
      {d20 === 1 && outcome !== 'fumble' && <span className="text-sm text-[var(--bad)]">Natural 1</span>}
    </div>
  )
}

function SingleRoll({ entry, settled, shown, done, showTiles, rate }: { entry: RollEntry; settled: boolean; shown: number; done: boolean; showTiles: boolean; rate: number }) {
  const kept = entry.d20[entry.kept]
  const tiles = [
    ...entry.mods.map((m) => ({ label: m.label, value: signed(m.value), sub: undefined, tone: 'plain' as const })),
    ...entry.bonus.map((b) => ({ label: b.label, value: signed(b.value), sub: `${b.die} → ${b.faces.join('+')}`, tone: (b.value < 0 ? 'penalty' : 'bonus') as 'penalty' | 'bonus' })),
  ]
  const running = showTiles ? kept + tiles.slice(0, shown).reduce((n, t) => n + Number(t.value), 0) : entry.total
  const two = entry.d20.length > 1
  const flair = done && kept === 20 ? 'burst' : done && kept === 1 ? 'shake' : ''
  const tone = (face: number, counts: boolean): Tone => (!counts ? 'plain' : face === 20 ? 'gold' : face === 1 ? 'red' : 'plain')
  return (
    <>
      <div className={`relative flex items-end justify-center gap-3 py-2 ${flair}`}>
        {entry.d20.map((face, i) => {
          const counts = i === entry.kept
          const motion = settled && two ? (counts ? 'die-kept' : 'die-dropped') : ''
          const glow = entry.mode === 'advantage' ? 'var(--good)' : entry.mode === 'disadvantage' ? 'var(--bad)' : 'var(--gold)'
          return (
            <Die key={i} face={face} tone={tone(face, counts)} settled={settled} size={two ? 80 : 96} className={motion} glow={glow} rate={rate} />
          )
        })}
      </div>
      <ModeBadge mode={entry.mode} />
      <div className="pixel-font text-2xl tabular-nums" style={{ color: done ? 'var(--parchment)' : 'var(--dim)' }}>
        {settled ? running : '?'}
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        {showTiles && tiles.map((t, i) => (
          <Tile key={i} label={t.label} value={t.value} sub={t.sub} tone={t.tone} shown={i < shown} />
        ))}
      </div>
    </>
  )
}

/** A group roll (a fireball save): one row per creature. */
function RollRows({ rolls, settled, shown, showTiles, rate }: { rolls: RollEntry[]; settled: boolean; shown: number; showTiles: boolean; rate: number }) {
  return (
    <ul className="flex w-full flex-col gap-1">
      {rolls.map((r, i) => {
        const revealed = i < shown
        return (
          <li key={r.who} className={`flex items-center gap-2 border-2 border-[var(--border)] bg-[var(--panel-2)] px-2 py-1 ${revealed ? 'tile-in' : settled ? 'opacity-50' : ''}`}>
            <span className="min-w-0 flex-1 truncate">{r.name}</span>
            <span className="flex gap-1">
              {r.d20.map((face, j) => (
                <Die
                  key={j}
                  face={face}
                  tone={j === r.kept ? (face === 20 ? 'gold' : face === 1 ? 'red' : 'plain') : 'plain'}
                  settled={settled}
                  size={32}
                  rate={rate}
                  className={settled && r.d20.length > 1 && j !== r.kept ? 'die-dropped' : ''}
                />
              ))}
            </span>
            <span className="w-24 truncate text-right text-xs text-[var(--dim)]">
              {revealed && showTiles && [...r.mods.slice(1).map((m) => signed(m.value)), ...r.bonus.map((b) => `${signed(b.value)} ${b.label}`)].join(' ')}
              {revealed && r.mode !== 'normal' && ` ${r.mode === 'advantage' ? '▲' : '▼'}`}
            </span>
            <span className="pixel-font w-8 text-right text-sm tabular-nums">{revealed ? r.total : ''}</span>
            <span className="w-14 text-right text-sm" style={{ color: r.outcome ? OUTCOME_COLOR[r.outcome] : undefined }}>
              {revealed && r.outcome ? OUTCOME_TEXT[r.outcome] : ''}
            </span>
          </li>
        )
      })}
    </ul>
  )
}

/** A plain `uv run roll` (no breakdown): the dice in the tray, or one d20 shape and the total. */
function PlainRoll({ roll, hold, queued, onDone }: { roll: Roll; hold: number; queued: boolean; onDone: () => void }) {
  const prefs = usePrefs()
  const rows = useMemo(() => (prefs.dice === 'tray' ? plainRows(roll) : null), [prefs.dice, roll])
  return rows ? <PlainTray rows={rows} seq={roll.seq} hold={hold} queued={queued} onDone={onDone} /> : <PlainDie roll={roll} hold={hold} onDone={onDone} />
}

function PlainTray({ rows, seq, hold, queued, onDone }: { rows: TrayRow[]; seq: number; hold: number; queued: boolean; onDone: () => void }) {
  const { landed, onLanded, trayRef } = useTray(true)
  useDismiss(landed, hold, onDone)
  return (
    <Shell className="w-[28rem] max-w-[94vw]">
      <div role="status" aria-live="polite" onClick={() => (trayRef.current?.() ? undefined : onDone())} className="flex cursor-pointer flex-col items-center gap-2">
        <span className="sr-only">{`${rows[0].expr}: ${rows[0].total}`}</span>
        <DiceTray rows={rows} crit={false} seed={seq} queued={queued} onSettled={onLanded} skipRef={trayRef} />
      </div>
    </Shell>
  )
}

/** The d20 look for a plain roll: the d20 (two side by side with advantage or disadvantage: one kept, one dropped) and the total. */
function PlainDie({ roll, hold, onDone }: { roll: Roll; hold: number; onDone: () => void }) {
  const tm = timeScale(usePrefs())
  const rate = tm ? 1 / tm : 1
  const { settled, done, skip } = useReveal(0, tm)
  useDismiss(done, hold, onDone)
  const d20 = roll.dice.find((d) => d.die.endsWith('d20') && d.faces.length === 1)?.faces[0]
  const dropped = roll.dice.filter((d) => d.die === '1d20 dropped').flatMap((d) => d.faces)
  // The die lands on the d20 that was rolled (any face if the roll has none) and grows the total.
  const [face] = useState(() => d20 ?? 1 + Math.floor(Math.random() * 20))
  const tone: Tone = d20 === 20 ? 'gold' : d20 === 1 ? 'red' : 'plain'
  const two = dropped.length > 0
  const glow = two ? (d20 !== undefined && d20 >= dropped[0] ? 'var(--good)' : 'var(--bad)') : undefined
  return (
    <Shell className="flex items-center gap-3 !py-2">
      <div role="status" aria-live="polite" onClick={settled ? onDone : skip} className="flex cursor-pointer items-center gap-3">
        <div className="flex items-end gap-2">
          <Die face={face} label={roll.total} tone={tone} settled={settled} size={56} rate={rate} className={settled && two ? 'die-kept' : ''} glow={glow} />
          {dropped.map((f, i) => (
            <Die key={i} face={f} settled={settled} size={56} rate={rate} className={settled ? 'die-dropped' : ''} />
          ))}
        </div>
        <div className="flex flex-col">
          <span className="text-sm text-[var(--dim)]">
            {roll.expr}
            {settled && roll.dice.length > 0 && ` · ${roll.dice.map((d) => (d.die.endsWith('dropped') ? `dropped [${d.faces.join(', ')}]` : `[${d.faces.join(', ')}]`)).join(' ')}`}
            {settled && tone === 'gold' && ' · critical!'}
            {settled && tone === 'red' && ' · fumble'}
          </span>
        </div>
      </div>
    </Shell>
  )
}
