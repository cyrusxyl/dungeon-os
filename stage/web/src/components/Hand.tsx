import { Button } from '@/components/ui/8bit/button'
import { useState } from 'react'

import { CombatStatus } from '@/components/Status'
import type { Ability, HandView } from '@/lib/arena'
import type { PartyChar } from '@/lib/party'
import { type Skin, usePins } from '@/lib/hand'

const ICON: Record<string, string> = { sword: '⚔', flame: '✹', fist: '✊', eye: '◉', boot: '➤', shield: '⛨', spark: '✦', heart: '♥', hand: '✋' }

const Pip = ({ used, label }: { used: boolean; label: string }) => (
  <span className={`border px-1 ${used ? 'border-[var(--dim)] text-[var(--dim)] line-through' : 'border-[var(--gold)] text-[var(--gold)]'}`}>{label}</span>
)

const CAP = { action: 'var(--action)', bonus: 'var(--bonus-action)', reaction: 'var(--reaction)', free: 'var(--dim)' } as const

function Choice({ ab, skin, picked, onPick }: { ab: Ability; skin: Skin; picked: boolean; onPick: (ab: Ability) => void }) {
  const off = Boolean(ab.why)
  const base = `text-left border-2 ${picked ? 'border-[var(--gold)] bg-white/10' : 'border-[var(--border)]'} ${off ? 'opacity-50' : 'cursor-pointer hover:bg-white/10'}`
  const cards = skin === 'cards'
  return (
    <button type="button" aria-disabled={off} title={ab.why ?? ab.text} onClick={() => onPick(ab)} className={`${base} ${cards ? 'flex min-h-24 w-28 shrink-0 flex-col overflow-hidden' : 'flex w-full items-center gap-2 px-2 py-1'}`}>
      <i aria-hidden="true" className={cards ? 'block h-1 w-full shrink-0' : 'block h-6 w-1 shrink-0'} style={{ background: CAP[ab.cost] }} />
      <span className={`text-[11px] ${cards ? 'px-1 pt-1' : ''}`}>
        {ICON[ab.icon] ?? '✦'} {ab.name}
      </span>
      <span className={`text-[9px] text-[var(--dim)] ${cards ? 'px-1' : ''}`}>{ab.cost} · {ab.text}</span>
      {ab.stat && <span className={`text-[9px] ${cards ? 'px-1' : ''}`}>{ab.stat}</span>}
      {off && <span className={`text-[9px] text-[var(--bad)] ${cards ? 'px-1' : ''}`}>{ab.why}</span>}
    </button>
  )
}

/**
 * The hand: the pips, then the abilities as cards or a list. A tap on one that needs a target opens the list of
 * targets; one that needs a cell waits for a tap on the board; any other runs at once.
 */
/** Improvise: the player says what the character tries, and may name an object on the board. The DM rules on it. */
function ImproviseBox({ objects, onSend, onCancel }: { objects: { id: string; name: string }[]; onSend: (text: string, object?: string) => void; onCancel: () => void }) {
  const [text, setText] = useState('')
  const [object, setObject] = useState<string>()
  return (
    <form
      className="flex flex-wrap items-center gap-1"
      aria-label="Improvise"
      onSubmit={(e) => {
        e.preventDefault()
        if (text.trim()) onSend(text.trim(), object)
      }}
    >
      <input autoFocus value={text} onChange={(e) => setText(e.target.value)} maxLength={300} placeholder="I throw the bottle in the goblin's face…" className="min-w-40 flex-1 border-2 border-[var(--border)] bg-black px-2 py-1 text-xs" />
      {objects.map((o) => (
        <Button key={o.id} type="button" size="sm" variant={object === o.id ? 'default' : 'outline'} onClick={() => setObject(object === o.id ? undefined : o.id)} className="text-[10px]" title="The object you use">
          {o.name}
        </Button>
      ))}
      <Button type="submit" size="sm" disabled={!text.trim()} className="text-[10px]">
        Ask the DM
      </Button>
      <Button type="button" size="sm" variant="outline" onClick={onCancel} className="text-[10px]">
        Cancel
      </Button>
    </form>
  )
}

export function Hand({ hand, skin, onSkin, selected, objects, onPick, onTarget, onImprovise, onCancel, status, onEnd }: { status?: PartyChar | null; onEnd?: () => void; hand: HandView; skin: Skin; onSkin: () => void; selected: Ability | null; objects: { id: string; name: string }[]; onPick: (ab: Ability) => void; onTarget: (ab: Ability, target: string, amount?: number) => void; onImprovise: (text: string, object?: string) => void; onCancel: () => void }) {
  const [drawer, setDrawer] = useState(false)
  const [amount, setAmount] = useState(1)
  // The hand: class abilities and weapons, up to three pinned items, Items, then Improvise.
  const rows = hand.abilities.filter((ab) => ab.source === 'item')
  const [pinned, togglePin] = usePins(hand.who, rows.map((ab) => ab.id))
  const improvise = hand.abilities.find((ab) => ab.id === 'improvise')
  const shown = [...hand.abilities.filter((ab) => ab.source !== 'item' && ab.id !== 'improvise'), ...rows.filter((ab) => pinned.includes(ab.id))]
  return (
    <div className="flex max-h-[40%] shrink-0 flex-col gap-1 overflow-y-auto border-t-2 border-[var(--border)] bg-black/85 p-2 text-xs" aria-label="Your hand">
      {status ? <CombatStatus c={status} /> : null}
      <div className="flex items-center gap-2 text-[10px]">
        {!status && (
          <>
            <Pip used={hand.turn.action} label="Action" />
            <Pip used={hand.turn.bonus} label="Bonus" />
            <Pip used={hand.turn.reaction} label="Reaction" />
          </>
        )}
        {hand.feet_left !== null && <span className="text-[var(--dim)]">{hand.feet_left} ft left</span>}
        <Button size="sm" variant="outline" className="ml-auto text-[10px]" onClick={onSkin}>
          {skin === 'cards' ? 'List' : 'Cards'}
        </Button>
        {onEnd && hand.current === hand.who && (
          <Button size="sm" className="text-[10px]" onClick={onEnd}>
            End turn
          </Button>
        )}
      </div>
      {selected?.needs === 'target' && (
        <div className="flex flex-wrap items-center gap-1" aria-label={`Targets for ${selected.name}`}>
          <span>{selected.name}:</span>
          {selected.amount !== undefined && (
            <label className="flex items-center gap-1">
              Points (1 to {selected.amount})
              <input
                type="number"
                min={1}
                max={selected.amount}
                value={Math.min(amount, selected.amount)}
                onChange={(e) => setAmount(Math.max(1, Math.min(selected.amount ?? 1, Number(e.target.value) || 1)))}
                className="w-16 border-2 border-[var(--border)] bg-[var(--ink)] px-1"
              />
            </label>
          )}
          {selected.targets?.length ? (
            selected.targets.map((t) => (
              <Button key={t.id} size="sm" variant="outline" disabled={!t.ok} title={t.why ?? undefined} onClick={() => onTarget(selected, t.id, selected.amount === undefined ? undefined : Math.min(amount, selected.amount))} className="text-[10px]">
                {t.name}{t.dist_ft === undefined ? '' : ` · ${t.dist_ft} ft`}{t.odds ? ` · ${t.odds}` : ''}
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
      {selected?.needs === 'text' && <ImproviseBox objects={objects} onSend={onImprovise} onCancel={onCancel} />}
      {selected?.needs === 'aim' && (
        <div className="flex items-center gap-2">
          <span>Tap a cell on the board to aim {selected.name}.</span>
          <Button size="sm" variant="outline" onClick={onCancel} className="text-[10px]">
            Cancel
          </Button>
        </div>
      )}
      {drawer && (
        <div className="flex flex-col gap-1 border-2 border-[var(--border)] p-1" aria-label="Items">
          {rows.map((ab) => (
            <div key={ab.id} className={`flex items-center gap-2 ${ab.why ? 'opacity-50' : ''}`}>
              <span className="flex-1">
                {ab.name} <span className="text-[var(--dim)]">· {ab.cost} · {ab.text}</span>
                {ab.why && <span className="text-[var(--bad)]"> · {ab.why}</span>}
              </span>
              <Button size="sm" variant="outline" disabled={Boolean(ab.why)} onClick={() => onPick(ab)} className="text-[10px]">
                Use
              </Button>
              <Button size="sm" variant={pinned.includes(ab.id) ? 'default' : 'outline'} aria-pressed={pinned.includes(ab.id)} onClick={() => togglePin(ab.id)} className="text-[10px]" title="Keep it in your hand">
                Pin
              </Button>
            </div>
          ))}
        </div>
      )}
      <div className={skin === 'cards' ? 'flex gap-1 overflow-x-auto' : 'flex flex-col gap-1'}>
        {shown.map((ab) => (
          <Choice key={ab.id} ab={ab} skin={skin} picked={selected?.id === ab.id} onPick={onPick} />
        ))}
        {rows.length > 0 && <Choice ab={{ id: 'items', name: 'Items', cost: 'free', kind: 'items', icon: 'spark', text: `${rows.length} usable`, stat: '', why: null, needs: 'none' }} skin={skin} picked={drawer} onPick={() => setDrawer(!drawer)} />}
        {improvise && <Choice ab={improvise} skin={skin} picked={selected?.id === improvise.id} onPick={onPick} />}
      </div>
    </div>
  )
}
