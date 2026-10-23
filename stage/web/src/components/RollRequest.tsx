import { useEffect, useRef, useState } from 'react'

import { Die } from '@/components/Die'
import { Shell, Tile } from '@/components/DiceOverlay'
import { GiveBonus } from '@/components/PartyPanel'
import { act, type Party, signed, TONE } from '@/lib/party'
import { postJson, type RerollOffer as Offer, type RollRequest as Request } from '@/lib/stage'

/**
 * The window before a roll the DM asked for. Like Baldur's Gate 3, the player sees the target number and every
 * tile that will add to the d20, can add a bonus (Guidance, Bless, advantage...) or leave one off, and clicks Roll.
 * `blocked` is the reason the button is off (shown on the button), or null when the player can roll.
 */
export function RollRequest({ request, party, refresh, blocked }: { request: Request; party: Party | null; refresh: () => void; blocked: string | null }) {
  const [skip, setSkip] = useState<string[]>([])
  const [rolling, setRolling] = useState(false)
  const button = useRef<HTMLButtonElement>(null)
  const canRoll = !blocked
  const char = party?.characters.find((c) => c.id === request.who)
  const catalogue = party?.effects ?? []
  // The effects on the character that this kind of roll uses.
  const applies = (char?.effects ?? []).map((id) => catalogue.find((e) => e.id === id)).filter((e) => e && e.on.includes(request.kind))

  useEffect(() => {
    if (canRoll) button.current?.focus()
  }, [canRoll])

  const roll = async () => {
    setRolling(true)
    const ok = (await postJson('/api/roll', { skip })).ok
    if (!ok) setRolling(false) // refused: the DM is busy, or the request is gone
  }
  const toggle = (id: string) => setSkip((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))

  return (
    <Shell className="w-[24rem] max-w-[94vw]">
      <div role="dialog" aria-label={`${request.title} roll`} className="flex flex-col items-center gap-2">
        <span className="text-sm text-[var(--dim)]">{request.name}</span>
        <h2 className="pixel-font text-sm text-[var(--parchment)]">{request.title}</h2>
        {request.subtitle && <p className="text-[var(--ember)]">{request.subtitle}</p>}
        {request.dc !== undefined && !request.hide && (
          <div className="flex flex-col items-center border-y-2 border-[var(--border)] px-8 py-1">
            <span className="text-[11px] tracking-widest text-[var(--dim)] uppercase">Difficulty Class</span>
            <span className="pixel-font text-xl tabular-nums">{request.dc}</span>
          </div>
        )}
        <Die face={20} label="?" settled size={96} />
        <div className="flex flex-wrap justify-center gap-2">
          {request.mods.map((m, i) => (
            <Tile key={i} label={m.label} value={signed(m.value)} tone="plain" shown />
          ))}
        </div>

        <div className="flex w-full flex-col items-center gap-1 border-t-2 border-[var(--border)] pt-2">
          <span className="text-[11px] tracking-widest text-[var(--dim)] uppercase">Bonuses</span>
          <div className="flex flex-wrap justify-center gap-2">
            {applies.length === 0 && <span className="text-sm text-[var(--dim)]">None</span>}
            {applies.map((e) =>
              e ? (
                <button
                  key={e.id}
                  type="button"
                  aria-pressed={!skip.includes(e.id)}
                  onClick={() => toggle(e.id)}
                  title={e.info}
                  className="border-2 px-2 py-1 text-sm leading-none"
                  style={{
                    borderColor: skip.includes(e.id) ? 'var(--border)' : TONE[e.tone],
                    color: skip.includes(e.id) ? 'var(--dim)' : TONE[e.tone],
                    textDecoration: skip.includes(e.id) ? 'line-through' : undefined,
                  }}
                >
                  {e.label}
                </button>
              ) : null,
            )}
            <GiveBonus
              offers={char?.offers ?? []}
              catalogue={catalogue}
              kind={request.kind}
              onGive={(o) => act('/api/effects', { who: request.who, from: o.from, effect: o.effect }, refresh)}
            />
          </div>
        </div>

        <button
          ref={button}
          type="button"
          onClick={roll}
          disabled={!canRoll || rolling}
          className="pixel-font mt-1 border-4 border-[var(--gold)] bg-[var(--gold)] px-6 py-2 text-xs text-[var(--ink)] hover:bg-[var(--parchment)] disabled:opacity-50"
        >
          {rolling ? 'Rolling…' : blocked ?? 'Roll'}
        </button>
      </div>
    </Shell>
  )
}

/**
 * The roll failed and the character has inspiration. The roll shows behind this window; the DM has not heard it yet.
 * Reroll spends one point and the new roll is final. Keep sends the roll as it fell.
 */
export function RerollOffer({ offer, blocked }: { offer: Offer; blocked: string | null }) {
  const [busy, setBusy] = useState(false)
  const [ready, setReady] = useState(false)
  // The failed roll is still tumbling in the roll window: wait, so the offer does not give the result away.
  useEffect(() => {
    const t = setTimeout(() => setReady(true), 3000)
    return () => clearTimeout(t)
  }, [])
  const answer = async (use: boolean) => {
    setBusy(true)
    if (!(await postJson('/api/roll/reroll', { use })).ok) setBusy(false) // refused: the offer is gone
  }
  if (!ready) return null
  return (
    <Shell low className="w-[22rem] max-w-[94vw]">
      <div role="dialog" aria-label="Reroll" className="flex flex-col items-center gap-2">
        <span className="text-sm text-[var(--dim)]">{offer.name ?? offer.who}</span>
        <h2 className="pixel-font text-sm text-[var(--ember)]">The roll failed</h2>
        <p className="text-center text-sm">Spend inspiration to roll again? The new roll is final. You have {offer.left} left.</p>
        <div className="mt-1 flex gap-3">
          <button
            type="button"
            autoFocus
            onClick={() => answer(true)}
            disabled={Boolean(blocked) || busy}
            className="pixel-font border-4 border-[var(--gold)] bg-[var(--gold)] px-4 py-2 text-xs text-[var(--ink)] hover:bg-[var(--parchment)] disabled:opacity-50"
          >
            {blocked ?? 'Reroll ✦'}
          </button>
          <button
            type="button"
            onClick={() => answer(false)}
            disabled={Boolean(blocked) || busy}
            className="pixel-font border-4 border-[var(--border)] px-4 py-2 text-xs text-[var(--parchment)] hover:border-[var(--gold)] disabled:opacity-50"
          >
            Keep
          </button>
        </div>
      </div>
    </Shell>
  )
}
