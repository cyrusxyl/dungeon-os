import { useEffect, useState } from 'react'

import { ConsoleDrawer } from '@/components/Console'
import { DialogueBox } from '@/components/DialogueBox'
import { PartyPanel } from '@/components/PartyPanel'
import { StageView } from '@/components/StageView'
import { Button } from '@/components/ui/8bit/button'
import { Input } from '@/components/ui/8bit/input'
import { sendInput, titleCase, useStage } from '@/lib/stage'

const STATUS_TEXT: Record<string, string> = {
  starting: 'The DM is getting ready…',
  busy: 'The DM is thinking…',
  idle: 'Your move.',
  waiting: 'The DM needs an answer in the console.',
  exited: 'The DM session ended.',
}

export default function App() {
  const { state, campaign, connected } = useStage()
  const [readSeq, setReadSeq] = useState<number | null>(null)
  const [draft, setDraft] = useState('')
  const [consoleOpen, setConsoleOpen] = useState(false)
  const [showParty, setShowParty] = useState(true)

  // On first load (or reload) everything already on record counts as read.
  useEffect(() => {
    if (state && readSeq === null) setReadSeq(state.log.at(-1)?.seq ?? 0)
  }, [state, readSeq])

  useEffect(() => {
    if (state?.dm.status === 'waiting') setConsoleOpen(true)
  }, [state?.dm.status])

  if (!state) {
    return <div className="pixel-font grid h-full place-items-center text-xs text-[var(--dim)]">Connecting to the table…</div>
  }

  const log = state.log
  const unread = log.filter((l) => l.seq > (readSeq ?? 0))
  const current = unread[0] ?? log.at(-1)
  const pending = Math.max(0, unread.length - 1)
  const caughtUp = unread.length <= 1
  const speaker = current?.type === 'say' ? current.actor : undefined
  const canType = state.dm.status === 'idle'
  const choices = caughtUp ? state.choices?.options : undefined

  const advance = () => setReadSeq(unread[0]?.seq ?? readSeq)
  const submit = async (text: string) => {
    const t = text.trim()
    if (!t || !canType) return
    setDraft('')
    setReadSeq(log.at(-1)?.seq ?? readSeq)
    await sendInput(t)
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
          {connected ? STATUS_TEXT[state.dm.status] : 'Reconnecting…'}
        </span>
        <Button size="sm" variant="outline" onClick={() => setShowParty((v) => !v)} className="hidden text-[10px] lg:inline-flex">
          Party
        </Button>
        <Button size="sm" variant="outline" onClick={() => setConsoleOpen((v) => !v)} className="text-[10px]">
          Console
        </Button>
      </header>

      <main className={`grid min-h-0 flex-1 gap-4 ${showParty ? 'lg:grid-cols-[1fr_20rem]' : ''}`}>
        <section className="flex min-h-0 flex-col gap-3">
          <div className="min-h-48 flex-1 border-4 border-[var(--border)] bg-black">
            <StageView state={state} speaker={speaker} />
          </div>
          <DialogueBox line={current} pending={pending} onAdvance={advance} />

          {state.dm.status === 'exited' ? (
            <div className="flex items-center gap-3">
              <span className="text-[var(--dim)]">The DM session ended.</span>
              <Button onClick={() => fetch('/api/restart', { method: 'POST' })} className="text-[10px]">
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
                <div className="min-w-0 flex-1">
                <Input
                  id="player-input"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder={canType ? 'What do you do?' : STATUS_TEXT[state.dm.status]}
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
          )}
        </section>
        {showParty && (
          <div className="hidden min-h-0 lg:flex">
            <PartyPanel />
          </div>
        )}
      </main>

      <ConsoleDrawer open={consoleOpen} onClose={() => setConsoleOpen(false)} dmLog={state.dm_log} />
    </div>
  )
}
