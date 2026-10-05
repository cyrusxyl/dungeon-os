import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/8bit/button'
import { Input } from '@/components/ui/8bit/input'
import { postJson } from '@/lib/stage'

interface Campaign {
  slug: string
  name: string
  in_progress: boolean
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

type Panel = 'main' | 'load' | 'new' | 'settings'

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
  const [framework, setFramework] = useState(data.settings.agent_framework)
  const [model, setModel] = useState(data.settings.model)

  useEffect(() => setError(''), [panel])

  const start = async (body: { campaign?: string; new_name?: string; pitch?: string; party?: string }) => {
    setBusy(true)
    setError('')
    const res = await post('/api/game/start', body)
    setBusy(false)
    if (res.error) setError(String(res.error))
    else onStarted()
  }

  const saveSettings = async () => {
    const res = await post('/api/settings', { agent_framework: framework, model })
    if (res.error) setError(String(res.error))
    else {
      onChanged(res as unknown as MenuData)
      setPanel('main')
    }
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
            <Button disabled={!data.resume || busy} onClick={() => data.resume && start({ campaign: data.resume.slug })} className="text-[10px]">
              {data.resume ? `Resume — ${data.resume.name}` : 'Resume'}
            </Button>
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
                  <Button variant="outline" disabled={busy} onClick={() => start({ campaign: c.slug })} className="w-full justify-between text-[10px]">
                    <span>{c.name}</span>
                    <span className="text-[var(--dim)]">{c.in_progress ? 'in progress' : 'new'}</span>
                  </Button>
                </li>
              ))}
            </ul>
          </Panel>
        )}

        {panel === 'new' && (
          <Panel title="New Game" onBack={() => setPanel('main')}>
            <form
              className="flex flex-col gap-4"
              onSubmit={(e) => {
                e.preventDefault()
                if (newName.trim() && !needsPitch) start({ new_name: newName.trim(), pitch: pitch.trim(), party })
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
            <Input id="model" list="model-presets" value={model} onChange={(e) => setModel(e.target.value)} font="normal" className="text-lg" />
            <datalist id="model-presets">
              {fw?.models.map((m) => <option key={m} value={m} />)}
            </datalist>
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
