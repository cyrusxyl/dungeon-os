import { Button } from '@/components/ui/8bit/button'
import type { Ability, HandView } from '@/lib/arena'
import type { Skin } from '@/lib/hand'

const ICON: Record<string, string> = { sword: '⚔', flame: '✹', fist: '✊', eye: '◉', boot: '➤', shield: '⛨', spark: '✦' }

const Pip = ({ used, label }: { used: boolean; label: string }) => (
  <span className={`border px-1 ${used ? 'border-[var(--dim)] text-[var(--dim)] line-through' : 'border-[var(--gold)] text-[var(--gold)]'}`}>{label}</span>
)

function Choice({ ab, skin, picked, onPick }: { ab: Ability; skin: Skin; picked: boolean; onPick: (ab: Ability) => void }) {
  const off = Boolean(ab.why)
  const base = `text-left border-2 ${picked ? 'border-[var(--gold)] bg-white/10' : 'border-[var(--border)]'} ${off ? 'opacity-50' : 'cursor-pointer hover:bg-white/10'}`
  return (
    <button type="button" aria-disabled={off} title={ab.why ?? ab.text} onClick={() => onPick(ab)} className={`${base} ${skin === 'cards' ? 'flex h-24 w-28 shrink-0 flex-col p-1' : 'flex w-full items-center gap-2 px-2 py-1'}`}>
      <span className="text-[11px]">
        {ICON[ab.icon] ?? '✦'} {ab.name}
      </span>
      <span className="text-[9px] text-[var(--dim)]">{ab.cost} · {ab.text}</span>
      {ab.stat && <span className="text-[9px]">{ab.stat}</span>}
      {off && <span className="text-[9px] text-[var(--bad)]">{ab.why}</span>}
    </button>
  )
}

/**
 * The hand: the pips, then the abilities as cards or a list. A tap on one that needs a target opens the list of
 * targets; one that needs a cell waits for a tap on the board; any other runs at once.
 */
export function Hand({ hand, skin, onSkin, selected, onPick, onTarget, onCancel }: { hand: HandView; skin: Skin; onSkin: () => void; selected: Ability | null; onPick: (ab: Ability) => void; onTarget: (ab: Ability, target: string) => void; onCancel: () => void }) {
  return (
    <div className="flex max-h-[40%] shrink-0 flex-col gap-1 overflow-y-auto border-t-2 border-[var(--border)] bg-black/85 p-2 text-xs" aria-label="Your hand">
      <div className="flex items-center gap-2 text-[10px]">
        <Pip used={hand.turn.action} label="Action" />
        <Pip used={hand.turn.bonus} label="Bonus" />
        <Pip used={hand.turn.reaction} label="Reaction" />
        <span className="text-[var(--dim)]">{hand.feet_left} ft left</span>
        <Button size="sm" variant="outline" className="ml-auto text-[10px]" onClick={onSkin}>
          {skin === 'cards' ? 'List' : 'Cards'}
        </Button>
      </div>
      {selected?.needs === 'target' && (
        <div className="flex flex-wrap items-center gap-1" aria-label={`Targets for ${selected.name}`}>
          <span>{selected.name}:</span>
          {selected.targets?.length ? (
            selected.targets.map((t) => (
              <Button key={t.id} size="sm" variant="outline" disabled={!t.ok} title={t.why ?? undefined} onClick={() => onTarget(selected, t.id)} className="text-[10px]">
                {t.name} · {t.dist_ft} ft{t.odds ? ` · ${t.odds}` : ''}
              </Button>
            ))
          ) : (
            <span className="text-[var(--dim)]">no target in sight</span>
          )}
          <Button size="sm" variant="outline" onClick={onCancel} className="text-[10px]">
            Cancel
          </Button>
        </div>
      )}
      {selected?.needs === 'aim' && (
        <div className="flex items-center gap-2">
          <span>Tap a cell on the board to aim {selected.name}.</span>
          <Button size="sm" variant="outline" onClick={onCancel} className="text-[10px]">
            Cancel
          </Button>
        </div>
      )}
      <div className={skin === 'cards' ? 'flex gap-1 overflow-x-auto' : 'flex flex-col gap-1'}>
        {hand.abilities.map((ab) => (
          <Choice key={ab.id} ab={ab} skin={skin} picked={selected?.id === ab.id} onPick={onPick} />
        ))}
      </div>
    </div>
  )
}
