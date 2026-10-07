import { JoinQr } from '@/components/JoinQr'
import { Button } from '@/components/ui/8bit/button'
import type { Party } from '@/lib/party'
import type { Me } from '@/lib/seats'
import { postJson, type StageState } from '@/lib/stage'

/** The first party is being made. The table shows who is here and the code to join; each phone makes its own character. */
export function Lobby({ state, party, me, table, status }: { state: StageState; party: Party | null; me: Me; table: boolean; status: string }) {
  const characters = party?.characters ?? []
  const making = state.creators.length
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto border-4 border-[var(--border)] bg-[var(--panel)] p-4">
      <h2 className="pixel-font text-xs text-[var(--gold)]">Gather the party</h2>
      <p className="pixel-font animate-pulse text-[10px] text-[var(--ember)]">{status}</p>
      {table && <JoinQr />}
      <ul className="flex flex-col gap-2">
        {characters.map((c) => (
          <li key={c.id} className="flex items-center gap-3 border-2 border-[var(--border)] p-2">
            <img src={`/asset/actor/${encodeURIComponent(c.id)}/portrait/neutral.png`} alt="" className="pixelated size-12 border-2 border-[var(--border)] bg-black" onError={(e) => (e.currentTarget.style.visibility = 'hidden')} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-xl">{c.name}</span>
              <span className="block truncate text-sm text-[var(--dim)]">
                {c.race} {c.class} · {state.seats.find((s) => s.who === c.id)?.player ?? 'no player yet'}
              </span>
            </span>
          </li>
        ))}
        {characters.length === 0 && <li className="text-[var(--dim)]">Nobody has made a character yet.</li>}
      </ul>
      {making > 0 && <p className="text-[var(--dim)]">{making === 1 ? 'One player is' : `${making} players are`} making a character.</p>}
      <div className="flex flex-wrap items-center gap-3">
        {!table && !state.creators.includes(me.sid) && (
          <Button variant="outline" onClick={() => postJson('/api/creation/open')} className="text-[10px]">
            {me.mine.length ? 'Make another character' : 'Make a character'}
          </Button>
        )}
        {me.host ? (
          <Button disabled={characters.length === 0} onClick={() => postJson('/api/creation/done', { force: true })} title="Everyone who made a character joins. The DM opens the first scene." className="text-[10px]">
            Start the adventure
          </Button>
        ) : (
          <span className="text-[var(--dim)]">The host starts the adventure when everyone is ready.</span>
        )}
      </div>
    </div>
  )
}
