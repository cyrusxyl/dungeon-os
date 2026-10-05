// The party panel, the roll window and the character sheet all read /api/party (stage/party.py).
import { useCallback, useState } from 'react'

import { postJson, useJson } from '@/lib/stage'

export interface EffectPreset {
  id: string
  label: string
  info: string
  concentration: boolean
  on: string[]
  tone: 'good' | 'bad' | 'gold'
}

export interface Item {
  name: string
  quantity: number
  weight: number
  equipped: boolean
  description: string
  rarity: 'common' | 'uncommon' | 'rare' | 'very rare' | 'legendary' | null
}

export interface PartyChar {
  id: string
  name: string
  race: string
  class: string
  level: number
  background?: string
  hp: { current?: number; max?: number; temp?: number }
  armor_class: number
  speed: number
  initiative: number
  prof: number
  abilities: Record<string, { score: number; mod: number; save: number; save_prof: boolean }>
  skills: { name: string; ability: string; bonus: number; prof: 0 | 1 | 2 }[]
  weapons: { name: string; attack_bonus?: number; damage?: string; damage_type?: string; properties?: string[]; equipped?: boolean }[]
  armor?: { name: string; ac_bonus?: number; type?: string; equipped?: boolean } | null
  inventory: Item[]
  capacity: number
  spell: { ability?: string; dc?: number; attack?: number; slots: Record<string, { max: number; remaining: number }>; known: string[] } | null
  resources: { name: string; max: number; recharge: 'short' | 'long'; used: number }[]
  features: { name: string; description?: string }[]
  death_saves?: { successes: number; failures: number } | null
  effects: string[]
  conditions: string[]
  /** What the character has used this turn (true = used); null outside a combat. */
  turn: { action: boolean; bonus: boolean; reaction: boolean } | null
}

export interface Party {
  characters: PartyChar[]
  location: string | null
  game_time: string | null
  quests: { title: string; status: string }[]
  effects: EffectPreset[]
  combat: { round: number; current: string | null; order: { id: string; name: string; initiative: number; pc: boolean }[] } | null
}

/** The party, read again each time the DM status changes (the DM writes the files during a turn) or after `refresh`. */
export function useParty(dmStatus: string): { party: Party | null; refresh: () => void } {
  const [bump, setBump] = useState(0)
  const party = useJson<Party>('/api/party', `${dmStatus}:${bump}`)
  const refresh = useCallback(() => setBump((n) => n + 1), [])
  return { party: party ?? null, refresh }
}

/** A change the player makes to their own character (stage/server.py). Resolves to false when the server refuses. */
export async function act(path: string, body: Record<string, unknown>, refresh: () => void): Promise<boolean> {
  const ok = (await postJson(path, body)).ok
  refresh()
  return ok
}

export const signed = (n: number) => (n >= 0 ? `+${n}` : `${n}`)

export const ROMAN = ['', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX']

/** The colour of an effect chip. */
export const TONE: Record<EffectPreset['tone'], string> = { good: 'var(--good)', bad: 'var(--bad)', gold: 'var(--gold)' }
