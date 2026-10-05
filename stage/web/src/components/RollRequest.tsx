import { useEffect, useRef, useState } from 'react'

import { D20 } from '@/components/D20'
import { Shell, Tile } from '@/components/DiceOverlay'
import { GiveBonus } from '@/components/PartyPanel'
import { act, type Party, signed, TONE } from '@/lib/party'
import { postJson, type RollRequest as Request } from '@/lib/stage'

/**
 * The window before a roll the DM asked for. Like Baldur's Gate 3, the player sees the target number and every
 * tile that will add to the d20, can add a bonus (Guidance, Bless, advantage...) or leave one off, and clicks Roll.
 */
export function RollRequest({ request, party, refresh, canRoll }: { request: Request; party: Party | null; refresh: () => void; canRoll: boolean }) {
  const [skip, setSkip] = useState<string[]>([])
  const [rolling, setRolling] = useState(false)
  const button = useRef<HTMLButtonElement>(null)
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
        <D20 value="?" className="size-24" />
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
          {rolling ? 'Rolling…' : canRoll ? 'Roll' : 'Wait for the DM…'}
        </button>
      </div>
    </Shell>
  )
}
