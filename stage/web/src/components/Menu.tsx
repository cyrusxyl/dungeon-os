import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/8bit/button'
import { Input } from '@/components/ui/8bit/input'
import { write } from '@/lib/local'
import { postJson } from '@/lib/stage'
import { defaultMode } from '@/lib/view'

const CUSTOM = '__custom__' // the model dropdown's "type your own" entry

interface Campaign {
  slug: string
  name: string
  in_progress: boolean
  can_continue: boolean // the DM's last conversation can be picked up again
  last_played: number // unix time; the list comes newest first
}

interface Save {
  id: string
  time: number
  kind: 'auto' | 'save' | 'load' | ''
  label: string
}

interface Framework {
  key: string
  label: string
  available: boolean
  models: string[]
}

export interface MenuData {
  game: string | null
  campaigns: Campaign[]
  resume: Campaign | null
  settings: { agent_framework: string; model: string }
  frameworks: Framework[]
}

type Panel = 'main' | 'load' | 'campaign' | 'new' | 'settings'

async function post(url: string, body: unknown): Promise<Record<string, unknown>> {
  return (await postJson(url, body)).json()
}

function Panel({ title, children, onBack }: { title: string; children: React.ReactNode; onBack: () => void }) {
  return (
    <div className="flex w-full flex-col gap-4">
      <h2 className="pixel-font text-xs text-[var(--gold)]">{title}</h2>
      {children}
      <button type="button" onClick={onBack} className="pixel-font self-start text-[10px] text-[var(--dim)] hover:text-[var(--parchment)]">
        ◀ Back
      </button>
    </div>
  )
}

export function Menu({ data, onStarted, onChanged }: { data: MenuData; onStarted: () => void; onChanged: (d: MenuData) => void }) {
  const [panel, setPanel] = useState<Panel>('main')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [newName, setNewName] = useState('')
  const [pitch, setPitch] = useState('')
  const [party, setParty] = useState<'create' | 'premade'>('create')
  const [play, setPlay] = useState<'here' | 'phones'>('here')
  const [framework, setFramework] = useState(data.settings.agent_framework)
  const [model, setModel] = useState(data.settings.model)
  const [picked, setPicked] = useState<Campaign | null>(null)
  const [saves, setSaves] = useState<Save[] | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  // A saved model outside the presets is edited as Custom, so it is never lost.
  const [custom, setCustom] = useState(
    () => !data.frameworks.find((f) => f.key === data.settings.agent_framework)?.models.includes(data.settings.model),
  )

  useEffect(() => setError(''), [panel])

  const start = async (
    body: { campaign?: string; dm?: 'continue' | 'fresh'; save?: string; new_name?: string; pitch?: string; party?: string; play?: 'here' | 'phones' },
    url = '/api/game/start',
  ) => {
    setBusy(true)
    setError('')
    const res = await post(url, body)
    setBusy(false)
    if (res.error) setError(String(res.error))
    else onStarted()
  }

  const pick = async (c: Campaign) => {
    setPicked(c)
    setConfirmDelete(false)
    setSaves(null)
    setPanel('campaign')
    const res = await fetch(`/api/saves/${c.slug}`)
    setSaves(res.ok ? (await res.json()).saves : [])
  }

  const deleteCampaign = async (c: Campaign) => {
    setBusy(true)
    const res = await post('/api/campaign/delete', { campaign: c.slug })
    setBusy(false)
    if (res.error) return setError(String(res.error))
    onChanged(res as unknown as MenuData)
    setConfirmDelete(false)
    setPanel('load')
  }

  const saveSettings = async () => {
    const res = await post('/api/settings', { agent_framework: framework, model: model.trim() })
    if (res.error) setError(String(res.error))
    else {
      onChanged(res as unknown as MenuData)
      setPanel('main')
    }
  }

  // The screen that starts a game says what it is: a place to play, or the shared table that phones join.
  const begin = () => {
    write('dungeon-view', play === 'phones' ? 'table' : defaultMode())
    start({ new_name: newName.trim(), pitch: pitch.trim(), party, play })
  }

  const needsPitch = party === 'premade' && !pitch.trim()
  const fw = data.frameworks.find((f) => f.key === framework)

  return (
    <div className="relative grid h-full place-items-center overflow-hidden p-4">
      <img
        src="/asset/template/tavern.png?mood=night"
        alt=""
        className="pixelated absolute inset-0 h-full w-full object-cover opacity-60"
        onError={(e) => (e.currentTarget.style.display = 'none')}
      />
      <div className="absolute inset-0 bg-gradient-to-b from-[var(--ink)]/40 via-transparent to-[var(--ink)]/90" aria-hidden="true" />

      <main className="relative flex w-full max-w-md flex-col items-center gap-8 border-4 border-[var(--gold)] bg-[var(--panel)]/95 p-6 sm:p-8">
        <header className="flex flex-col items-center gap-3 text-center">
          <h1 className="pixel-font text-xl leading-relaxed text-[var(--gold)] sm:text-2xl">DungeonOS</h1>
          <p className="text-lg text-[var(--dim)]">An AI dungeon master at a pixel table</p>
        </header>

        {panel === 'main' && (
          <nav className="flex w-full flex-col gap-4">
            {data.resume?.can_continue && (
              <Button disabled={busy} onClick={() => start({ campaign: data.resume!.slug, dm: 'continue' })} className="text-[10px]">
                Continue — {data.resume.name}
              </Button>
            )}
            <Button
              variant={data.resume?.can_continue ? 'outline' : 'default'}
              disabled={!data.resume || busy}
              onClick={() => data.resume && start({ campaign: data.resume.slug, dm: 'fresh' })}
              className="text-[10px]"
            >
              {data.resume ? `${data.resume.can_continue ? 'New DM session' : 'Resume'} — ${data.resume.name}` : 'Resume'}
            </Button>
            {data.resume?.can_continue && (
              <p className="text-center text-sm text-[var(--dim)]">Continue keeps the DM's conversation (faster). A new DM session reads the campaign files again.</p>
            )}
            <Button variant="outline" disabled={busy || data.campaigns.length === 0} onClick={() => setPanel('load')} className="text-[10px]">
              Load Game
            </Button>
            <Button variant="outline" disabled={busy} onClick={() => setPanel('new')} className="text-[10px]">
              New Game
            </Button>
            <Button variant="outline" disabled={busy} onClick={() => setPanel('settings')} className="text-[10px]">
              Settings
            </Button>
            {!data.resume && <p className="text-center text-sm text-[var(--dim)]">No campaign in progress yet. Load one or start a new game.</p>}
          </nav>
        )}

        {panel === 'load' && (
          <Panel title="Load Game" onBack={() => setPanel('main')}>
            <ul className="flex flex-col gap-3">
              {data.campaigns.map((c) => (
                <li key={c.slug}>
                  <Button variant="outline" disabled={busy} onClick={() => pick(c)} className="w-full justify-between text-[10px]">
                    <span>{c.name}</span>
                    <span className="text-[var(--dim)]">
                      {c.in_progress ? new Date(c.last_played * 1000).toLocaleDateString([], { dateStyle: 'short' }) : 'new'}
                    </span>
                  </Button>
                </li>
              ))}
            </ul>
          </Panel>
        )}

        {panel === 'campaign' && picked && (
          <Panel title={picked.name} onBack={() => setPanel('load')}>
            <div className="flex flex-col gap-3">
              {picked.can_continue && (
                <Button disabled={busy} onClick={() => start({ campaign: picked.slug, dm: 'continue' })} className="text-[10px]">
                  Continue the DM session
                </Button>
              )}
              <Button
                variant={picked.can_continue ? 'outline' : 'default'}
                disabled={busy}
                onClick={() => start({ campaign: picked.slug, dm: 'fresh' })}
                className="text-[10px]"
              >
                {picked.in_progress ? 'New DM session, from the files' : 'Start'}
              </Button>
            </div>
            <h3 className="pixel-font text-[10px] text-[var(--dim)]">Saves</h3>
            {saves === null && <p className="text-sm text-[var(--dim)]">Looking…</p>}
            {saves?.length === 0 && <p className="text-sm text-[var(--dim)]">No saves yet. The game saves after every DM turn.</p>}
            <ul className="flex max-h-64 flex-col gap-2 overflow-y-auto overflow-x-hidden pr-1">
              {saves?.map((v) => (
                <li key={v.id} className="flex items-center gap-2">
                  <span className="min-w-0 flex-1 text-sm">
                    <span className={v.kind === 'save' ? 'text-[var(--gold)]' : 'text-[var(--dim)]'}>
                      {new Date(v.time * 1000).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}
                      {v.kind === 'save' ? ' ★' : v.kind === 'load' ? ' ↩' : ''}
                    </span>
                    <span className="block truncate">{v.label}</span>
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy}
                    title="The game goes back to this point. A new DM session starts. The present is saved first."
                    onClick={() => start({ campaign: picked.slug, save: v.id }, '/api/game/load')}
                    className="text-[10px]"
                  >
                    Load
                  </Button>
                </li>
              ))}
            </ul>
            <div className="flex flex-col gap-2 border-t-2 border-[var(--border)] pt-3">
              {!confirmDelete ? (
                <Button variant="outline" disabled={busy} onClick={() => setConfirmDelete(true)} className="text-[10px] text-red-400">
                  Delete campaign
                </Button>
              ) : (
                <>
                  <p className="text-sm text-red-400">Delete {picked.name} and all its saves? This cannot be undone.</p>
                  <div className="flex gap-2">
                    <Button disabled={busy} onClick={() => deleteCampaign(picked)} className="flex-1 text-[10px]">
                      Yes, delete
                    </Button>
                    <Button variant="outline" disabled={busy} onClick={() => setConfirmDelete(false)} className="flex-1 text-[10px]">
                      Cancel
                    </Button>
                  </div>
                </>
              )}
            </div>
          </Panel>
        )}

        {panel === 'new' && (
          <Panel title="New Game" onBack={() => setPanel('main')}>
            <form
              className="flex flex-col gap-4"
              onSubmit={(e) => {
                e.preventDefault()
                if (newName.trim() && !needsPitch) begin()
              }}
            >
              <label htmlFor="new-name" className="text-lg">
                Name the campaign. The DM starts with Session Zero.
              </label>
              <Input id="new-name" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="The Sunless Citadel" font="normal" className="text-lg" />
              <label htmlFor="new-pitch" className="text-lg">
                Pitch (optional)
              </label>
              <textarea
                id="new-pitch"
                rows={3}
                value={pitch}
                onChange={(e) => setPitch(e.target.value)}
                placeholder="An epilogue for my Baldur's Gate 3 party: Astarion, Shadowheart, Karlach…"
                className="w-full border-4 border-[var(--border)] bg-[var(--ink)] p-2 text-lg text-[var(--parchment)] focus:border-[var(--gold)] focus:outline-none"
              />
              <fieldset className="flex flex-col gap-2">
                <legend className="mb-2 text-lg">Who makes the party</legend>
                {([['create', 'I make my characters'], ['premade', 'The DM makes them from the pitch']] as const).map(([v, label]) => (
                  <label key={v} className="flex items-center gap-3 text-lg">
                    <input type="radio" name="party" value={v} checked={party === v} onChange={() => setParty(v)} className="accent-[var(--gold)]" />
                    {label}
                  </label>
                ))}
              </fieldset>
              <fieldset className="flex flex-col gap-2">
                <legend className="mb-2 text-lg">Who plays</legend>
                {([['here', 'I play on this screen'], ['phones', 'Friends join on their phones. This screen is the shared table.']] as const).map(([v, label]) => (
                  <label key={v} className="flex items-center gap-3 text-lg">
                    <input type="radio" name="play" value={v} checked={play === v} onChange={() => setPlay(v)} className="accent-[var(--gold)]" />
                    {label}
                  </label>
                ))}
                {play === 'phones' && ['localhost', '127.0.0.1'].includes(location.hostname) && (
                  <p className="text-sm text-[var(--ember)]">Phones cannot open this address. Open this page by the server's network address (start it with --lan).</p>
                )}
              </fieldset>
              {needsPitch && <p className="text-sm text-[var(--ember)]">Write a pitch so the DM knows which characters to make.</p>}
              <Button type="submit" disabled={busy || !newName.trim() || needsPitch} className="text-[10px]">
                Begin
              </Button>
            </form>
          </Panel>
        )}

        {panel === 'settings' && (
          <Panel title="Settings" onBack={() => setPanel('main')}>
            <fieldset className="flex flex-col gap-2">
              <legend className="mb-2 text-lg">Who runs the DM</legend>
              {data.frameworks.map((f) => (
                <label key={f.key} className={`flex items-center gap-3 text-lg ${f.available ? '' : 'opacity-50'}`}>
                  <input
                    type="radio"
                    name="framework"
                    value={f.key}
                    checked={framework === f.key}
                    disabled={!f.available}
                    onChange={() => {
                      setFramework(f.key)
                      setModel(f.models[0] ?? '')
                      setCustom(false)
                    }}
                    className="accent-[var(--gold)]"
                  />
                  {f.label}
                  {!f.available && <span className="text-sm text-[var(--dim)]">(not installed)</span>}
                </label>
              ))}
            </fieldset>
            <label htmlFor="model" className="text-lg">
              Model
            </label>
            <div className="relative border-y-6 border-foreground">
              <select
                id="model"
                value={custom ? CUSTOM : model}
                onChange={(e) => {
                  if (e.target.value === CUSTOM) setCustom(true)
                  else {
                    setCustom(false)
                    setModel(e.target.value)
                  }
                }}
                className="w-full cursor-pointer bg-[var(--panel)] px-3 py-2 text-lg text-[var(--gold)] outline-none"
              >
                {fw?.models.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
                <option value={CUSTOM}>Custom…</option>
              </select>
              <div className="pointer-events-none absolute inset-0 -mx-1.5 border-x-6 border-foreground" aria-hidden="true" />
            </div>
            {custom && (
              <Input
                aria-label="Custom model"
                placeholder="alias or full model id (empty = the CLI default)"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                font="normal"
                className="text-lg"
              />
            )}
            <Button onClick={saveSettings} className="text-[10px]">
              Save
            </Button>
          </Panel>
        )}

        {busy && <p className="pixel-font animate-pulse text-[10px] text-[var(--ember)]">Calling the DM to the table…</p>}
        {error && <p role="alert" className="text-lg text-red-400">{error}</p>}
      </main>
    </div>
  )
}
