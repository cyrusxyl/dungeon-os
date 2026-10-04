import { memo } from 'react'

import { Progress } from '@/components/ui/8bit/progress'
import { useJson } from '@/lib/stage'

interface Party {
  location: string | null
  game_time: string | null
  quests: { title: string; status: string }[]
  characters: {
    id: string
    name: string
    race: string
    class: string
    level: number
    armor_class: number
    hp: { current?: number; max?: number; temp?: number }
    inventory: { name: string; quantity: number }[]
  }[]
}

/** The party sheet; read again each time the DM status changes (the DM writes the files during a turn). */
export const PartyPanel = memo(function PartyPanel({ dmStatus }: { dmStatus: string }) {
  const party = useJson<Party>('/api/party', dmStatus)
  if (!party) return null

  return (
    <aside className="flex flex-col gap-4 overflow-y-auto border-4 border-[var(--border)] bg-[var(--panel)] p-4">
      {party.location && (
        <section>
          <h2 className="pixel-font text-[10px] text-[var(--gold)]">Where</h2>
          <p className="mt-1 text-lg">{party.location}</p>
          {party.game_time && <p className="text-[var(--dim)]">{party.game_time}</p>}
        </section>
      )}
      {party.characters.map((c) => {
        const cur = c.hp.current ?? 0
        const max = c.hp.max || 1
        return (
          <section key={c.id} className="flex flex-col gap-2">
            <div className="flex items-baseline justify-between gap-2">
              <h2 className="pixel-font text-[10px] text-[var(--gold)]">{c.name}</h2>
              <span className="text-sm text-[var(--dim)]">AC {c.armor_class}</span>
            </div>
            <p className="text-[var(--dim)]">
              {c.race} {c.class} · lvl {c.level}
            </p>
            <div className="flex items-center gap-3">
              <Progress value={(cur / max) * 100} variant="retro" className="h-3 flex-1" progressBg="bg-[var(--ember)]" />
              <span className="text-sm tabular-nums">
                {cur}/{max}
                {c.hp.temp ? ` +${c.hp.temp}` : ''}
              </span>
            </div>
            <ul className="text-sm text-[var(--parchment)]/80">
              {c.inventory.map((i) => (
                <li key={i.name}>
                  • {i.name}
                  {i.quantity > 1 ? ` ×${i.quantity}` : ''}
                </li>
              ))}
            </ul>
          </section>
        )
      })}
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
