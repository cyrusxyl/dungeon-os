import { useCallback, useEffect, useRef, useState } from 'react'

import { D20 } from '@/components/D20'
import type { Roll, RollDetail, RollEntry } from '@/lib/stage'

// The roll window plays like the one in Baldur's Gate 3: the dice tumble and land, advantage drops the lower die,
// then each tile adds to the total, one by one, and the result lands last.
const TUMBLE_MS = 900
const SETTLE_MS = 700
const TILE_MS = 280
const HOLD_MS = 4500
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

const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

/**
 * Where the roll animation is. `settled`: the dice have landed. `shown`: how many of `count` tiles have landed.
 * `done`: everything is on screen. With reduced motion it starts done.
 */
function useReveal(count: number): { settled: boolean; shown: number; done: boolean } {
  const [step, setStep] = useState(() => (reducedMotion() ? count + 2 : 0))
  useEffect(() => {
    if (step >= count + 2) return
    const t = window.setTimeout(() => setStep(step + 1), step === 0 ? TUMBLE_MS : step === 1 ? SETTLE_MS : TILE_MS)
    return () => window.clearTimeout(t)
  }, [step, count])
  return { settled: step >= 1, shown: Math.min(Math.max(step - 1, 0), count), done: step >= count + 2 }
}

/** Random faces for `n` dice, changing a dozen times a second while `on`. */
function useShuffle(n: number, on: boolean): number[] {
  const [faces, setFaces] = useState<number[]>(() => Array.from({ length: n }, () => 1 + Math.floor(Math.random() * 20)))
  useEffect(() => {
    if (!on) return
    const t = window.setInterval(() => setFaces(Array.from({ length: n }, () => 1 + Math.floor(Math.random() * 20))), 80)
    return () => window.clearInterval(t)
  }, [n, on])
  return faces
}

const signed = (n: number) => (n >= 0 ? `+${n}` : `${n}`)

/** Plays each roll the stage has not shown yet, one after the other. */
export function DiceOverlay({ rolls }: { rolls: Roll[] }) {
  // Rolls already on record when the page loads are history, not news.
  const seen = useRef(rolls.at(-1)?.seq ?? 0)
  const [queue, setQueue] = useState<Roll[]>([])

  useEffect(() => {
    const fresh = rolls.filter((r) => r.seq > seen.current)
    if (!fresh.length) return
    seen.current = fresh[fresh.length - 1].seq
    setQueue((q) => [...q, ...fresh])
  }, [rolls])

  // Stable: every state snapshot renders this again, and a new function would restart the hold timer.
  const next = useCallback(() => setQueue((q) => q.slice(1)), [])
  const roll = queue[0]
  if (!roll) return null
  const hold = queue.length > 1 ? QUEUED_HOLD_MS : HOLD_MS
  return roll.detail ? (
    <RollWindow key={roll.seq} detail={roll.detail} hold={hold} onDone={next} />
  ) : (
    <PlainRoll key={roll.seq} roll={roll} hold={hold} onDone={next} />
  )
}

function useDismiss(done: boolean, hold: number, onDone: () => void) {
  useEffect(() => {
    if (!done) return
    const t = window.setTimeout(onDone, hold)
    return () => window.clearTimeout(t)
  }, [done, hold, onDone])
}

export function Tile({ label, value, sub, tone, shown }: { label: string; value: string; sub?: string; tone: 'plain' | 'bonus' | 'penalty'; shown: boolean }) {
  const border = tone === 'bonus' ? 'border-[var(--gold)]' : tone === 'penalty' ? 'border-[var(--bad)]' : 'border-[var(--border)]'
  return (
    <div className={`flex w-[4.75rem] flex-col items-center gap-1 border-2 bg-[var(--panel-2)] px-1 py-2 text-center ${border} ${shown ? 'tile-in' : 'invisible'}`}>
      <span className="pixel-font text-xs tabular-nums" style={{ color: tone === 'penalty' ? 'var(--bad)' : tone === 'bonus' ? 'var(--gold)' : 'var(--parchment)' }}>
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

export function Shell({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className="pointer-events-none fixed inset-0 z-40 flex items-start justify-center pt-[8vh]">
      <div className={`dice-pop pointer-events-auto relative border-4 border-[var(--gold)] bg-[var(--panel)] px-5 py-4 ${className}`}>{children}</div>
    </div>
  )
}

/** The roll window: a check, a saving throw, an attack or a death save, with every tile that makes the total. */
function RollWindow({ detail, hold, onDone }: { detail: RollDetail; hold: number; onDone: () => void }) {
  const group = detail.rolls.length > 1
  const tileCount = group ? detail.rolls.length : detail.rolls[0].mods.length + detail.rolls[0].bonus.length
  const { settled, shown, done } = useReveal(tileCount)
  useDismiss(done, hold, onDone)
  const dice = group ? detail.rolls.reduce((n, r) => n + r.d20.length, 0) : detail.rolls[0].d20.length
  const shuffle = useShuffle(dice, !settled)

  const summary = detail.rolls.map((r) => `${r.name} ${r.total}${r.outcome ? ` ${OUTCOME_TEXT[r.outcome]}` : ''}`).join(', ')
  return (
    <Shell className={group ? 'w-[28rem] max-w-[94vw]' : 'w-[22rem] max-w-[94vw]'}>
      <div role="status" aria-live="polite" onClick={onDone} className="flex cursor-pointer flex-col items-center gap-2">
        <span className="sr-only">{`${detail.title}. ${summary}`}</span>
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
          <RollRows rolls={detail.rolls} shuffle={shuffle} settled={settled} shown={shown} />
        ) : (
          <SingleRoll entry={detail.rolls[0]} shuffle={shuffle} settled={settled} shown={shown} done={done} />
        )}
        {done && !group && detail.rolls[0].outcome && <Result outcome={detail.rolls[0].outcome} d20={detail.rolls[0].d20[detail.rolls[0].kept]} />}
        {done && detail.damage && (
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

function SingleRoll({ entry, shuffle, settled, shown, done }: { entry: RollEntry; shuffle: number[]; settled: boolean; shown: number; done: boolean }) {
  const kept = entry.d20[entry.kept]
  const tiles = [
    ...entry.mods.map((m) => ({ label: m.label, value: signed(m.value), sub: undefined, tone: 'plain' as const })),
    ...entry.bonus.map((b) => ({ label: b.label, value: signed(b.value), sub: `${b.die} → ${b.faces.join('+')}`, tone: (b.value < 0 ? 'penalty' : 'bonus') as 'penalty' | 'bonus' })),
  ]
  const running = kept + tiles.slice(0, shown).reduce((n, t) => n + Number(t.value), 0)
  const two = entry.d20.length > 1
  const flair = done && kept === 20 ? 'burst' : done && kept === 1 ? 'shake' : ''
  const tone = (face: number, counts: boolean) => (!counts ? 'plain' : face === 20 ? 'gold' : face === 1 ? 'red' : 'plain')
  return (
    <>
      <div className={`relative flex items-end justify-center gap-3 py-2 ${flair}`}>
        {entry.d20.map((face, i) => {
          const counts = i === entry.kept
          const motion = !settled ? 'die-tumble' : two ? (counts ? 'die-kept' : 'die-dropped') : ''
          const glow = entry.mode === 'advantage' ? 'var(--good)' : entry.mode === 'disadvantage' ? 'var(--bad)' : 'var(--gold)'
          return (
            <D20
              key={i}
              value={settled ? face : shuffle[i]}
              tone={settled ? tone(face, counts) : 'plain'}
              className={`${two ? 'size-20' : 'size-24'} ${motion}`}
              glow={glow}
            />
          )
        })}
      </div>
      <ModeBadge mode={entry.mode} />
      <div className="pixel-font text-2xl tabular-nums" style={{ color: done ? 'var(--parchment)' : 'var(--dim)' }}>
        {settled ? running : '?'}
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        {tiles.map((t, i) => (
          <Tile key={i} label={t.label} value={t.value} sub={t.sub} tone={t.tone} shown={i < shown} />
        ))}
      </div>
    </>
  )
}

/** A group roll (a fireball save): one row per creature. */
function RollRows({ rolls, shuffle, settled, shown }: { rolls: RollEntry[]; shuffle: number[]; settled: boolean; shown: number }) {
  // Where each row's dice start in the shuffled faces.
  const starts = rolls.map((_, i) => rolls.slice(0, i).reduce((n, r) => n + r.d20.length, 0))
  return (
    <ul className="flex w-full flex-col gap-1">
      {rolls.map((r, i) => {
        const first = starts[i]
        const revealed = i < shown
        return (
          <li key={r.who} className={`flex items-center gap-2 border-2 border-[var(--border)] bg-[var(--panel-2)] px-2 py-1 ${revealed ? 'tile-in' : settled ? 'opacity-50' : ''}`}>
            <span className="min-w-0 flex-1 truncate">{r.name}</span>
            <span className="flex gap-1">
              {r.d20.map((face, j) => (
                <D20
                  key={j}
                  value={settled ? face : shuffle[first + j]}
                  tone={settled && j === r.kept ? (face === 20 ? 'gold' : face === 1 ? 'red' : 'plain') : 'plain'}
                  className={`size-8 ${!settled ? 'die-tumble' : r.d20.length > 1 && j !== r.kept ? 'die-dropped' : ''}`}
                />
              ))}
            </span>
            <span className="w-24 truncate text-right text-xs text-[var(--dim)]">
              {revealed && [...r.mods.slice(1).map((m) => signed(m.value)), ...r.bonus.map((b) => `${signed(b.value)} ${b.label}`)].join(' ')}
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

/** A plain `uv run roll` (no breakdown): the dice and the total. */
function PlainRoll({ roll, hold, onDone }: { roll: Roll; hold: number; onDone: () => void }) {
  const { settled, done } = useReveal(0)
  useDismiss(done, hold, onDone)
  const face = useShuffle(1, !settled)[0]
  const d20 = roll.dice.find((d) => d.die.endsWith('d20') && d.faces.length === 1)?.faces[0]
  const tone = settled && d20 === 20 ? 'gold' : settled && d20 === 1 ? 'red' : 'plain'
  return (
    <Shell className="flex items-center gap-3 !py-2">
      <div role="status" aria-live="polite" onClick={onDone} className="flex cursor-pointer items-center gap-3">
        <D20 value={settled ? roll.total : face} tone={tone} className={`size-14 ${settled ? '' : 'die-tumble'}`} />
        <div className="flex flex-col">
          <span className="text-sm text-[var(--dim)]">
            {roll.expr}
            {settled && roll.dice.length > 0 && ` · ${roll.dice.map((d) => (d.die.endsWith('dropped') ? `dropped [${d.faces.join(', ')}]` : `[${d.faces.join(', ')}]`)).join(' ')}`}
            {tone === 'gold' && ' · critical!'}
            {tone === 'red' && ' · fumble'}
          </span>
        </div>
      </div>
    </Shell>
  )
}
