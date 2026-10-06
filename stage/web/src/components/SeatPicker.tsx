import { useState } from 'react'

import { Button } from '@/components/ui/8bit/button'
import { Input } from '@/components/ui/8bit/input'
import type { Party } from '@/lib/party'
import type { Me } from '@/lib/seats'
import { useHint } from '@/lib/hint'
import { recallSeats, rememberSeats, saveName, savedName } from '@/lib/seats'
import { postJson, type Seat } from '@/lib/stage'

/** The join screen: a player types a name and sits at a free character, or makes a new one. */
export function SeatPicker({ campaign, party, seats, me, onClose, onNew }: { campaign: string; party: Party | null; seats: Seat[]; me: Me; onClose: () => void; onNew: () => void }) {
  const [name, setName] = useState(savedName)
  const [error, setError] = useState('')
  const { hint, tip } = useHint()
  const owner = (id: string) => seats.find((s) => s.who === id)
  const free = (party?.characters ?? []).filter((c) => !owner(c.id))

  const leave = async (who: string) => {
    const res = await postJson('/api/seat/release', { who })
    if (res.ok) rememberSeats(campaign, recallSeats(campaign).filter((id) => id !== who))
  }

  const take = async (ids: string[]) => {
    const player = name.trim() || 'Player'
    saveName(player)
    const results = await Promise.all(ids.map((who) => postJson('/api/seat/claim', { who, name: player })))
    const bad = results.find((r) => !r.ok)
    setError(bad ? ((await bad.json().catch(() => null))?.error ?? 'The seat is taken.') : '')
  }

  return (
    <div role="dialog" aria-label="Pick your seat" className="fixed inset-0 z-50 grid place-items-center bg-black/80 p-4">
      <div className="flex max-h-full w-full max-w-md flex-col gap-3 overflow-y-auto border-4 border-[var(--gold)] bg-[var(--panel)] p-4">
        <h2 className="pixel-font text-xs text-[var(--gold)]">Pick your seat</h2>
        <Input aria-label="Your name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" font="normal" className="text-lg" />
        <ul className="flex flex-col gap-2">
          {(party?.characters ?? []).map((c) => {
            const o = owner(c.id)
            return (
              <li key={c.id} className="flex items-center gap-2 border-2 border-[var(--border)] p-2">
                <img src={`/asset/actor/${encodeURIComponent(c.id)}/portrait/neutral.png`} alt="" className="pixelated size-10 border-2 border-[var(--border)] bg-black" onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-lg">{c.name}</span>
                  <span className="block truncate text-sm text-[var(--dim)]">
                    {c.race} {c.class} {c.level}
                  </span>
                </span>
                {o ? (
                  <span className="flex items-center gap-2 text-sm text-[var(--dim)]">
                    {o.sid === me.sid ? 'You' : o.player}
                    {(o.sid === me.sid || me.host) && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => leave(c.id)}
                        {...tip(o.sid === me.sid ? `Give up ${c.name}. Someone else can play them.` : `Remove ${o.player} from ${c.name}. Use it when that player has left.`)}
                        className="text-[10px]"
                      >
                        {o.sid === me.sid ? 'Leave' : 'Free'}
                      </Button>
                    )}
                  </span>
                ) : (
                  <Button size="sm" onClick={() => take([c.id])} {...tip(`Play ${c.name}. Your actions and rolls will be for this character only.`)} className="text-[10px]">
                    Play
                  </Button>
                )}
              </li>
            )
          })}
          {!party && <li className="text-[var(--dim)]">Loading the party…</li>}
          {party && party.characters.length === 0 && <li className="text-[var(--dim)]">No characters yet. Make one.</li>}
        </ul>
        {error && <p role="alert" className="text-[var(--bad)]">{error}</p>}
        <div className="flex flex-wrap gap-2">
          <Button onClick={onNew} {...tip('Make a new character and play it. The party gains one member.')} className="text-[10px]">
            New character
          </Button>
          {free.length > 1 && (
            <Button variant="outline" onClick={() => take(free.map((c) => c.id))} {...tip('Play every character that nobody plays yet. Use it when you play alone.')} className="text-[10px]">
              Play all free
            </Button>
          )}
          <Button
            variant="outline"
            onClick={onClose}
            {...tip(
              me.mine.length
                ? 'Close this window. Your seats stay.'
                : me.host
                  ? 'Show the game without playing a character. Use it on the shared screen.'
                  : 'Look at the game without playing a character. You cannot act or talk to the DM.',
            )}
            className="text-[10px]"
          >
            {me.mine.length ? 'Close' : me.host ? 'Run the table' : 'Watch only'}
          </Button>
        </div>
        <p className="min-h-10 text-sm text-[var(--dim)]" aria-live="polite">
          {hint || 'Point at a button to see what it does.'}
        </p>
      </div>
    </div>
  )
}
