import { useEffect, useRef, useState } from 'react'

import { CharacterCreator } from '@/components/CharacterCreator'
import { ConsoleDrawer } from '@/components/Console'
import { CrawlView } from '@/components/CrawlView'
import { DialogueBox } from '@/components/DialogueBox'
import { JoinQr } from '@/components/JoinQr'
import { HostControls } from '@/components/HostControls'
import { LogDrawer } from '@/components/LogDrawer'
import { MapOverlay } from '@/components/MapOverlay'
import { Card, PartyPanel } from '@/components/PartyPanel'
import { RollRequest } from '@/components/RollRequest'
import { SeatPicker } from '@/components/SeatPicker'
import { SheetDrawer } from '@/components/SheetDrawer'
import { StageView } from '@/components/StageView'
import { TurnBar } from '@/components/TurnBar'
import { Button } from '@/components/ui/8bit/button'
import { Input } from '@/components/ui/8bit/input'
import { useParty } from '@/lib/party'
import { recall, remember, useMe } from '@/lib/seats'
import { type Layout, type Mode, useView } from '@/lib/view'
import { postJson, sendInput, titleCase, useStage } from '@/lib/stage'

const STATUS_TEXT: Record<string, string> = {
  starting: 'The DM is getting ready…',
  busy: 'The DM is thinking…',
  idle: 'Your move.',
  waiting: 'The DM needs an answer in the console.',
  exited: 'The DM session ended.',
}

export function GameView({ onMenu }: { onMenu: () => void }) {
  const { state, campaign, connected } = useStage(onMenu)
  const [confirmQuit, setConfirmQuit] = useState(false)
  // Save: null = closed, a string = the name being typed; `saved` flashes after a save.
  const [saveName, setSaveName] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  // End session: ask the DM to write the session record, then leave once it is idle again.
  const [ending, setEnding] = useState<'no' | 'sent' | 'working'>('no')
  const [logOpen, setLogOpen] = useState(false)
  const [readSeq, setReadSeq] = useState<number | null>(null)
  const [draft, setDraft] = useState('')
  const [consoleOpen, setConsoleOpen] = useState(false)
  const [mapOpen, setMapOpen] = useState(false)
  const [showParty, setShowParty] = useState(true)
  const [sheet, setSheet] = useState<string | null>(null)
  const { party, refresh } = useParty(state?.dm.status ?? 'starting')
  const me = useMe(state)
  const { mode, setMode, hand, setHand } = useView()
  const [viewOpen, setViewOpen] = useState(false)
  // A device with no seat can watch (the table screen does) instead of picking one.
  const [watching, setWatchingNow] = useState(false)
  const [seatOpen, setSeatOpen] = useState(false)
  const [chosen, setChosen] = useState<string | null>(null)

  const setWatching = (v: boolean) => {
    setWatchingNow(v)
    remember(campaign, 'watching', v)
  }
  // After a reload or a new game start, this browser sits back down at the seats it had, and keeps its choice to watch.
  const restored = useRef(false)
  useEffect(() => {
    if (!state || !me || !party || !campaign || restored.current) return
    restored.current = true
    setWatchingNow(recall(campaign, 'watching') as boolean)
    const name = (() => {
      try {
        return localStorage.getItem('dungeon-player-name') ?? ''
      } catch {
        return ''
      }
    })()
    for (const who of recall(campaign, 'seats') as string[]) {
      if (party.characters.some((c) => c.id === who) && !state.seats.some((s) => s.who === who)) postJson('/api/seat/claim', { who, name })
    }
  }, [state, me, party, campaign])
  useEffect(() => {
    if (me && restored.current && me.mine.length) remember(campaign, 'seats', me.mine)
  }, [me?.mine, campaign])

  // On first load (or reload) everything already on record counts as read.
  useEffect(() => {
    if (state && readSeq === null) setReadSeq(state.log.at(-1)?.seq ?? 0)
  }, [state, readSeq])

  useEffect(() => {
    if (state?.dm.status === 'waiting') setConsoleOpen(true)
  }, [state?.dm.status])

  useEffect(() => {
    const status = state?.dm.status
    if (ending === 'sent' && status === 'busy') setEnding('working')
    if (ending === 'working' && (status === 'idle' || status === 'exited')) {
      postJson('/api/game/quit').then(onMenu)
    }
  }, [ending, state?.dm.status, onMenu])

  const saveGame = async () => {
    const res = await postJson('/api/game/save', { name: saveName ?? '' })
    if (res.ok) {
      setSaveName(null)
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    }
  }

  if (!state) {
    return <div className="pixel-font grid h-full place-items-center text-xs text-[var(--dim)]">Connecting to the table…</div>
  }

  const log = state.log
  const unread = log.filter((l) => l.seq > (readSeq ?? 0))
  const current = unread[0] ?? log.at(-1)
  const pending = Math.max(0, unread.length - 1)
  const caughtUp = unread.length <= 1
  const speaker = current?.type === 'say' ? current.actor : undefined
  const mine = me?.mine ?? []
  const isHost = me?.host ?? false
  // The table screen only shows the game: it takes no input.
  const canType = state.dm.status === 'idle' && (isHost || mine.length > 0) && mode !== 'table'
  // Several seats on one device: the line goes to the DM as this character (the one on turn, if it is yours).
  const who = mine.includes(chosen ?? '') ? chosen! : mine.includes(party?.combat?.current ?? '') ? party!.combat!.current! : mine[0]
  const showCreator = state.creating && (state.creator === me?.sid || (state.creator === null && isHost))
  const picking = Boolean(me) && !showCreator && ((mine.length === 0 && !watching && mode !== 'table') || seatOpen)
  const choices = caughtUp ? state.choices?.options : undefined
  // Walking and travel wait until the player has read the story so far.
  const canAct = canType && caughtUp
  const waitingWorld = state.party_mode === 'premade' && log.length === 0 && ['starting', 'busy'].includes(state.dm.status)
  const activity = state.activity?.at(-1)
  const baseStatus = waitingWorld ? 'The DM is preparing the world and your party…' : STATUS_TEXT[state.dm.status]
  const statusText = activity && state.dm.status === 'busy' ? `${baseStatus.replace(/…$/, '')} — ${activity}…` : baseStatus

  const advance = () => setReadSeq(unread[0]?.seq ?? readSeq)
  const submit = async (text: string) => {
    const t = text.trim()
    if (!t || !canType) return
    setDraft('')
    setReadSeq(log.at(-1)?.seq ?? readSeq)
    await sendInput(t, mine.length ? who : undefined)
  }

  const inputBlock = (
    state.dm.status === 'exited' ? (
            <div className="flex items-center gap-3">
              <span className="text-[var(--dim)]">The DM session ended.</span>
              <Button onClick={() => postJson('/api/restart')} className="text-[10px]">
                Start a new DM session
              </Button>
            </div>
          ) : (
            <>
              {choices && (
                <div className="flex flex-wrap gap-3">
                  {choices.map((c) => (
                    <Button key={c} disabled={!canType} onClick={() => submit(c)} className="text-[10px]">
                      {c}
                    </Button>
                  ))}
                </div>
              )}
              <form
                className="flex gap-3"
                onSubmit={(e) => {
                  e.preventDefault()
                  submit(draft)
                }}
              >
                {mine.length > 1 && (
                  <select
                    aria-label="Speak as"
                    value={who}
                    onChange={(e) => setChosen(e.target.value)}
                    className="border-2 border-[var(--border)] bg-[var(--panel)] px-2 text-base"
                  >
                    {mine.map((id) => (
                      <option key={id} value={id}>
                        {party?.characters.find((c) => c.id === id)?.name ?? titleCase(id)}
                      </option>
                    ))}
                  </select>
                )}
                <div className="min-w-0 flex-1">
                <Input
                  id="player-input"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder={canType ? 'What do you do?' : mine.length === 0 && !isHost ? 'Take a seat to play.' : statusText}
                  disabled={!canType}
                  className="text-lg"
                  font="normal"
                />
                </div>
                <Button type="submit" disabled={!canType || !draft.trim()} className="text-[10px]">
                  Act
                </Button>
              </form>
            </>
          )
  )
  // The table screen has no input. It shows what the DM offers, so everyone at the table can read it.
  const tableChoices = choices ? (
    <p className="text-lg text-[var(--dim)]">
      The DM offers: <span className="text-[var(--parchment)]">{choices.join(' · ')}</span>
    </p>
  ) : null
  const overlays = (
    <>
      {state.roll_request && !showCreator && (
        <RollRequest key={state.roll_request.seq} request={state.roll_request} party={party} refresh={refresh} canRoll={canType && caughtUp && mine.includes(state.roll_request.who)} />
      )}
      {picking && me && (
        <SeatPicker
          campaign={campaign}
          party={party}
          seats={state.seats}
          me={me}
          onClose={() => {
            setWatching(true)
            setSeatOpen(false)
          }}
          onNew={() => postJson('/api/creation/open')}
        />
      )}
      {sheet && party && <SheetDrawer party={party} who={sheet} onWho={setSheet} onClose={() => setSheet(null)} />}
      <MapOverlay open={mapOpen} onClose={() => setMapOpen(false)} state={state} canAct={canAct} />
      <LogDrawer open={logOpen} onClose={() => setLogOpen(false)} log={state.log} />
      <ConsoleDrawer open={consoleOpen} onClose={() => setConsoleOpen(false)} dmLog={state.dm_log} />
    </>
  )
  const viewMenu = (
    <Button
      size="sm"
      variant="outline"
      onClick={() => setViewOpen((v) => !v)}
      title="Change how this device shows the game: full screen, shared table screen, or phone hand."
      className="text-[10px]"
    >
      View
    </Button>
  )
  const viewPanel = viewOpen && (
    <div className="flex flex-wrap items-center gap-3 border-2 border-[var(--border)] bg-[var(--panel)] p-2 text-base">
      <label className="flex items-center gap-2" title="Full: everything on one screen. Table: the shared screen, no input. Hand: this player's card on a phone.">
        Screen
        <select value={mode} onChange={(e) => setMode(e.target.value as Mode)} className="border-2 border-[var(--border)] bg-[var(--panel)] px-2">
          <option value="full">Full</option>
          <option value="table">Table (shared)</option>
          <option value="hand">Hand (phone)</option>
        </select>
      </label>
      {mode === 'hand' && (
        <>
          <label className="flex items-center gap-2" title="Show the scene and its picture above your card, as on the shared screen.">
            <input type="checkbox" checked={hand.scene} onChange={(e) => setHand({ ...hand, scene: e.target.checked })} />
            Show the scene
          </label>
          <label className="flex items-center gap-2" title="Auto follows how you hold the phone. Portrait stacks the parts. Landscape puts the scene beside your card.">
            Layout
            <select value={hand.layout} onChange={(e) => setHand({ ...hand, layout: e.target.value as Layout })} className="border-2 border-[var(--border)] bg-[var(--panel)] px-2">
              <option value="auto">Auto</option>
              <option value="portrait">Portrait</option>
              <option value="landscape">Landscape</option>
            </select>
          </label>
        </>
      )}
    </div>
  )
  if (mode === 'hand') {
    const layout =
      hand.layout === 'portrait'
        ? 'flex flex-col'
        : hand.layout === 'landscape'
          ? 'grid grid-cols-[1.3fr_1fr]'
          : 'flex flex-col landscape:grid landscape:grid-cols-[1.3fr_1fr]'
    const cards = (party?.characters ?? []).filter((c) => mine.includes(c.id))
    return (
      <div className="flex h-full flex-col gap-2 p-2">
        <header className="flex flex-wrap items-center gap-2">
          <span
            className={`size-2 shrink-0 ${!connected ? 'bg-red-500' : state.dm.status === 'idle' ? 'bg-emerald-400' : 'animate-pulse bg-[var(--ember)]'}`}
            aria-hidden="true"
          />
          <span className="min-w-0 flex-1 truncate text-sm text-[var(--dim)]">{connected ? statusText : 'Reconnecting…'}</span>
          {me && (
            <Button size="sm" variant="outline" onClick={() => { setWatching(false); setSeatOpen(true) }} title="Pick, leave or add a character that you play." className="text-[10px]">
              Seat
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={() => setMapOpen(true)} className="text-[10px]">
            Map
          </Button>
          <Button size="sm" variant="outline" onClick={() => setLogOpen((v) => !v)} className="text-[10px]">
            Log
          </Button>
          {viewMenu}
        </header>
        {viewPanel}
        <main className={`min-h-0 flex-1 gap-3 overflow-y-auto ${showCreator ? '' : layout}`}>
          {showCreator ? (
            <CharacterCreator dmStatus={state.dm.status} activity={state.activity?.at(-1)} />
          ) : (
            <>
              <section className="flex min-w-0 flex-col gap-2">
                {party && <TurnBar party={party} dmStatus={state.dm.status} />}
                {hand.scene && (
                  <div className="aspect-[320/192] w-full border-4 border-[var(--border)] bg-black">
                    {state.explore ? <CrawlView state={state} siteId={state.explore} canAct={canAct && !mapOpen} /> : <StageView state={state} speaker={speaker} />}
                  </div>
                )}
                <DialogueBox line={current} pending={pending} onAdvance={advance} versions={state.versions ?? {}} />
              </section>
              <section className="flex min-w-0 flex-col gap-2">
                {inputBlock}
                {party &&
                  cards.map((c) => (
                    <Card
                      key={c.id}
                      c={c}
                      party={party}
                      active={party.combat?.current === c.id}
                      canAct={canAct && !state.roll_request}
                      refresh={refresh}
                      onSheet={() => setSheet(c.id)}
                      seat={state.seats.find((x) => x.who === c.id)}
                      mineIds={mine}
                    />
                  ))}
                {me && mine.length === 0 && <p className="text-[var(--dim)]">You have no character. Tap Seat to pick one.</p>}
              </section>
            </>
          )}
        </main>
        {overlays}
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col gap-3 p-3 sm:p-4">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="pixel-font text-xs text-[var(--gold)]">DungeonOS</h1>
        <span className="text-lg text-[var(--dim)]">{titleCase(campaign)}</span>
        <span className="ml-auto flex items-center gap-2 text-sm text-[var(--dim)]">
          <span
            className={`size-2 ${!connected ? 'bg-red-500' : state.dm.status === 'idle' ? 'bg-emerald-400' : 'animate-pulse bg-[var(--ember)]'}`}
            aria-hidden="true"
          />
          {connected ? statusText : 'Reconnecting…'}
        </span>
        <Button size="sm" variant="outline" onClick={() => setShowParty((v) => !v)} className="hidden text-[10px] lg:inline-flex">
          Party
        </Button>
        {!state.creating && (
          <Button size="sm" variant="outline" onClick={() => postJson('/api/creation/open')} className="text-[10px]">
            New character
          </Button>
        )}
        <Button size="sm" variant="outline" onClick={() => setMapOpen(true)} className="text-[10px]">
          Map
        </Button>
        <Button size="sm" variant="outline" onClick={() => setLogOpen((v) => !v)} className="text-[10px]">
          Log
        </Button>
        {viewMenu}
        {me && <HostControls me={me} />}
        {me && mode !== 'table' && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setWatching(false)
              setSeatOpen(true)
            }}
            title="Pick, leave or add a character that you play."
            className="text-[10px]"
          >
            Seat
          </Button>
        )}
        {isHost && state.creating && !showCreator && (
          <Button size="sm" variant="outline" onClick={() => postJson('/api/creation/done')} title="Close the character creator that another device left open." className="text-[10px]">
            Close creator
          </Button>
        )}
        {isHost && (
          <Button size="sm" variant="outline" onClick={() => setConsoleOpen((v) => !v)} className="text-[10px]">
            Console
          </Button>
        )}
        {!isHost ? null : saveName !== null ? (
          <form
            className="flex items-center gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              saveGame()
            }}
          >
            <Input
              autoFocus
              aria-label="Save name"
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              placeholder="Name this save (optional)"
              font="normal"
              className="h-8 w-52 text-base"
            />
            <Button size="sm" type="submit" disabled={state.dm.status !== 'idle'} className="text-[10px]">
              Save
            </Button>
            <Button size="sm" type="button" variant="outline" onClick={() => setSaveName(null)} className="text-[10px]">
              Cancel
            </Button>
          </form>
        ) : (
          <Button size="sm" variant="outline" disabled={state.dm.status !== 'idle'} onClick={() => setSaveName('')} className="text-[10px]">
            {saved ? 'Saved ✓' : 'Save'}
          </Button>
        )}
        {!isHost ? null : ending !== 'no' ? (
          <span className="flex flex-wrap items-center gap-2">
            <span className="pixel-font animate-pulse text-[10px] text-[var(--ember)]">The DM is writing the session record…</span>
            {/* A way out if the DM never finishes (it exited, or never started the turn). */}
            <Button size="sm" variant="outline" onClick={() => postJson('/api/game/quit').then(onMenu)} className="text-[10px]">
              Leave without saving
            </Button>
          </span>
        ) : confirmQuit ? (
          <span className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              disabled={state.dm.status !== 'idle'}
              onClick={() => {
                setEnding('sent')
                sendInput(
                  'End the session now: follow the session-end procedure in the dm-canon-procedures skill ' +
                    '(one `uv run dnd-cli session end` with the recap), then say goodbye in one short beat.',
                  undefined,
                  true,
                )
              }}
              className="text-[10px]"
            >
              End session
            </Button>
            <Button size="sm" variant="outline" onClick={() => postJson('/api/game/quit').then(onMenu)} className="text-[10px]">
              Leave without saving
            </Button>
            <Button size="sm" variant="outline" onClick={() => setConfirmQuit(false)} className="text-[10px]">
              Stay
            </Button>
          </span>
        ) : (
          <Button size="sm" variant="outline" onClick={() => setConfirmQuit(true)} className="text-[10px]">
            Menu
          </Button>
        )}
      </header>
      {viewPanel}

      <main className={`grid min-h-0 flex-1 gap-4 ${showParty ? 'lg:grid-cols-[1fr_22rem]' : ''}`}>
        {showCreator ? (
          <section className="flex min-h-0 flex-col">
            <CharacterCreator dmStatus={state.dm.status} activity={state.activity?.at(-1)} />
          </section>
        ) : (
        <section className="flex min-h-0 flex-col gap-3">
          {party && <TurnBar party={party} dmStatus={state.dm.status} />}
          <div className="min-h-48 flex-1 border-4 border-[var(--border)] bg-black">
            {state.explore ? (
              <CrawlView state={state} siteId={state.explore} canAct={canAct && !mapOpen} />
            ) : (
              <StageView state={state} speaker={speaker} />
            )}
          </div>
          <DialogueBox line={current} pending={pending} onAdvance={advance} versions={state.versions ?? {}} />

          {mode === 'table' ? tableChoices : inputBlock}
        </section>
        )}
        {showParty && (
          <div className="hidden min-h-0 flex-col gap-3 lg:flex">
            {mode === 'table' && <JoinQr />}
            <div className="flex min-h-0 flex-1">
              <PartyPanel party={party} refresh={refresh} onSheet={setSheet} canAct={canAct && !state.roll_request} seats={state.seats} mine={mine} />
            </div>
          </div>
        )}
      </main>

      {overlays}
    </div>
  )
}
