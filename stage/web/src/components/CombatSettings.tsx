import { Button } from '@/components/ui/8bit/button'
import { setPrefs, usePrefs } from '@/lib/prefs'
import { postJson } from '@/lib/stage'

export interface CombatValues {
  reaction_seconds: number
  round_summary: boolean
}

const REACTION_TIMES = [0, 5, 10, 20, 30, 60]

/** The Combat tab of Settings. The walking pad is this device's; how long a player has to answer a reaction question, and the DM's one beat for each round, are the host's. */
export function CombatSettings({ values }: { values: CombatValues | null }) {
  const prefs = usePrefs()
  const set = (body: Record<string, unknown>) => postJson('/api/combat/settings', body)
  return (
    <>
      <p className="text-sm text-[var(--dim)]">The walking pad is for this device only. The other options are the host's and apply at once.</p>
      <label className="flex items-center gap-3 text-lg">
        <input type="checkbox" checked={prefs.pad} onChange={(e) => setPrefs({ pad: e.target.checked })} className="accent-[var(--gold)]" />
        Walking pad on the board
      </label>
      {values ? (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-lg">
              Reaction time
              <span className="block text-sm text-[var(--dim)]">How long a player has to answer an opportunity attack.</span>
            </span>
            <Button
              size="sm"
              variant="outline"
              className="text-[10px]"
              onClick={() => set({ reaction_seconds: REACTION_TIMES[(REACTION_TIMES.indexOf(values.reaction_seconds) + 1) % REACTION_TIMES.length] })}
            >
              {values.reaction_seconds ? `${values.reaction_seconds} s` : 'No limit'}
            </Button>
          </div>
          <label className="flex items-center gap-3 text-lg">
            <input type="checkbox" checked={values.round_summary} onChange={(e) => set({ round_summary: e.target.checked })} className="accent-[var(--gold)]" />
            <span>
              Round summary
              <span className="block text-sm text-[var(--dim)]">The DM tells one beat after each round.</span>
            </span>
          </label>
          <Button size="sm" variant="outline" className="self-start text-[10px]" onClick={() => set({ ...values, make_default: true })} title="Keep these for every game on this machine">
            Make default
          </Button>
        </>
      ) : (
        <p className="text-sm text-[var(--dim)]">Only the host changes the reaction time and the round summary.</p>
      )}
    </>
  )
}
