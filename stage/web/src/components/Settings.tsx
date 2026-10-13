import { useState } from 'react'

import { Button } from '@/components/ui/8bit/button'
import { Input } from '@/components/ui/8bit/input'
import { VoiceServer } from '@/components/VoiceServer'
import { Tabs, type Tab } from '@/components/Tabs'
import { VoiceToggle } from '@/components/VoiceToggle'
import { postJson } from '@/lib/stage'
import type { Mode } from '@/lib/view'

const CUSTOM = '__custom__' // the model dropdown's "type your own" entry

export interface Framework {
  key: string
  label: string
  available: boolean
  models: string[]
}

export interface SettingsData {
  agent_framework: string
  model: string
  voice: boolean
  voice_parts: VoiceParts
  tts_url: string
  tts_stop_on_exit: boolean
  tts_url_from_env: boolean
}

interface VoiceParts {
  narration: boolean
  npc: boolean
  player: boolean
}

const PARTS = [
  ['narration', 'Narration'],
  ['npc', 'NPC voices'],
  ['player', "Player characters' voices"],
] as const

/** The server-wide voice switches. The main menu and the in-game Settings both use it. */
function VoiceSettings({
  voice,
  parts,
  onVoice,
  onParts,
}: {
  voice: boolean
  parts: VoiceParts
  onVoice: (v: boolean) => void
  onParts: (p: VoiceParts) => void
}) {
  return (
    <>
      <label className="flex items-center gap-3 text-lg">
        <input type="checkbox" checked={voice} onChange={(e) => onVoice(e.target.checked)} className="accent-[var(--gold)]" />
        Voice
      </label>
      <p className="text-sm text-[var(--dim)]">Off: the game never contacts the voice service. Use this on a machine that has none.</p>
      {PARTS.map(([key, label]) => (
        <label key={key} className={`ml-6 flex items-center gap-3 text-lg ${voice ? '' : 'opacity-50'}`}>
          <input
            type="checkbox"
            checked={parts[key]}
            disabled={!voice}
            onChange={(e) => onParts({ ...parts, [key]: e.target.checked })}
            className="accent-[var(--gold)]"
          />
          {label}
        </label>
      ))}
    </>
  )
}

/**
 * The settings, as tabs. The main menu and the in-game Settings both use it.
 * `inGame`: the DM tab is left out (the DM is fixed while a session runs).
 * `settings` is null for a guest in a game: only this device's voice shows, and nothing is saved.
 */
export function Settings({
  settings,
  frameworks,
  inGame,
  mode,
  onSaved,
}: {
  settings: SettingsData | null
  frameworks: Framework[]
  inGame: boolean
  mode: Mode
  onSaved: (menu: { settings: SettingsData }) => void
}) {
  const [framework, setFramework] = useState(settings?.agent_framework ?? '')
  const [model, setModel] = useState(settings?.model ?? '')
  // Custom is on when the model is outside the presets (so a saved one is never lost), or when picked.
  const [customPicked, setCustomPicked] = useState(false)
  const [voice, setVoice] = useState(settings?.voice ?? true)
  const [parts, setParts] = useState(settings?.voice_parts ?? { narration: true, npc: true, player: false })
  const [ttsUrl, setTtsUrl] = useState(settings?.tts_url ?? '')
  const [stopOnExit, setStopOnExit] = useState(settings?.tts_stop_on_exit ?? false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)

  const save = async () => {
    setError('')
    const body: Record<string, unknown> = { voice, voice_parts: parts, tts_url: ttsUrl.trim(), tts_stop_on_exit: stopOnExit }
    if (!inGame) Object.assign(body, { agent_framework: framework, model: model.trim() })
    const res = await postJson('/api/settings', body)
    const data = await res.json().catch(() => null)
    if (!res.ok || data?.error) return setError(data?.error ?? 'Could not save.')
    setSaved(true)
    setTimeout(() => setSaved(false), 2500)
    onSaved(data)
  }

  const fw = frameworks.find((f) => f.key === framework)
  const custom = customPicked || !fw?.models.includes(model)
  const urlDirty = ttsUrl.trim() !== (settings?.tts_url ?? '')

  const dm: Tab = {
    id: 'dm',
    label: 'DM',
    body: (
      <>
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 text-lg">Who runs the DM</legend>
          {frameworks.map((f) => (
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
                  setCustomPicked(false)
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
              if (e.target.value === CUSTOM) setCustomPicked(true)
              else {
                setCustomPicked(false)
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
            onChange={(e) => {
              setCustomPicked(true)
              setModel(e.target.value)
            }}
            font="normal"
            className="text-lg"
          />
        )}
      </>
    ),
  }

  const voiceTab: Tab = {
    id: 'voice',
    label: 'Voice',
    body: (
      <>
        {settings && (
          <>
            <VoiceSettings voice={voice} parts={parts} onVoice={setVoice} onParts={setParts} />
            <h3 className="mt-2 text-lg text-[var(--gold)]">Voice service</h3>
            <label htmlFor="tts-url" className="text-lg">
              Service URL
            </label>
            <Input
              id="tts-url"
              value={ttsUrl}
              onChange={(e) => setTtsUrl(e.target.value)}
              placeholder="http://127.0.0.1:8770"
              disabled={settings.tts_url_from_env}
              font="normal"
              className="text-lg"
            />
            {settings.tts_url_from_env && <p className="text-sm text-[var(--dim)]">The DUNGEON_TTS_URL setting of the server wins over this field.</p>}
            <VoiceServer urlDirty={urlDirty} stopOnExit={stopOnExit} />
            <label className="flex items-center gap-3 text-lg">
              <input type="checkbox" checked={stopOnExit} onChange={(e) => setStopOnExit(e.target.checked)} className="accent-[var(--gold)]" />
              Stop it when the game server stops
            </label>
          </>
        )}
        <h3 className="mt-2 text-lg text-[var(--gold)]">This device</h3>
        <VoiceToggle mode={mode} />
      </>
    ),
  }

  const tabs = inGame ? [voiceTab] : [dm, voiceTab]
  return (
    <div className="flex flex-col gap-4">
      <Tabs tabs={tabs} label="Settings" />
      {settings && (
        <Button size="sm" onClick={save} className="self-start text-[10px]">
          {saved ? 'Saved ✓' : 'Save'}
        </Button>
      )}
      {error && (
        <p role="alert" className="text-lg text-red-400">
          {error}
        </p>
      )}
    </div>
  )
}
