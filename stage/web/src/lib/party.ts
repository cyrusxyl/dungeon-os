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
  /** A `stance` is something the character chose to do (Dodge, Hide); the rest are done to it. */
  conditions: { name: string; stance: boolean }[]
  in_combat: boolean
  /** What the character has used this turn (true = used). Always false outside a combat. */
  turn: { action: boolean; bonus: boolean; reaction: boolean }
  /** The common actions and class features; `why` says why one is greyed out. */
  actions: CardAction[]
  attacks: { name: string; bonus: number; damage: string }[]
  /** Bonuses a party member can really give this character right now. */
  offers: Offer[]
}

export interface CardAction {
  id: string
  label: string
  cost: 'action' | 'bonus' | null
  info: string
  target: 'enemy' | 'ally' | null
  why: string | null
  /** A short note for the card, such as the slots or points left. */
  stat?: string
  /** Lay on Hands: the points left in the pool. */
  left?: number | null
}

export interface Offer {
  effect: string
  from: string
  from_name: string
  cost: 'action' | 'bonus'
  slot: number | null
  why: string | null
}

export type Health = 'unhurt' | 'injured' | 'bloodied' | 'near death' | 'down'

export interface Entrant {
  id: string
  name: string
  initiative: number
  pc: boolean
  /** Its side in this fight: green party, yellow neutral faction, red hostile. */
  team: 'party' | 'neutral' | 'hostile'
  health: Health
  conditions: { name: string; stance: boolean }[]
}

export interface Party {
  characters: PartyChar[]
  location: string | null
  game_time: string | null
  quests: { title: string; status: string }[]
  effects: EffectPreset[]
  combat: { round: number; current: string | null; order: Entrant[] } | null
  /** Creatures on the stage that are not in the party: the targets of an Attack out of a fight, which starts one. */
  present?: { id: string; name: string }[]
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
  let res = await postJson(path, body)
  if (res.status === 409) {
    // An attack that starts a fight with someone at peace comes back as a question (`confirm`): ask, then send it again.
    const asked = (await res.clone().json().catch(() => null)) as { error?: string; confirm?: boolean } | null
    if (asked?.confirm && window.confirm(`${asked.error ?? 'This starts a fight.'}\n\nAttack anyway?`)) res = await postJson(path, { ...body, confirm: true })
  }
  refresh()
  return res.ok
}

/** How full a health bar is for a creature the players only see as a band, not as numbers. */
export const BAND_FILL: Record<Health, number> = { unhurt: 100, injured: 75, bloodied: 45, 'near death': 15, down: 0 }

export const signed = (n: number) => (n >= 0 ? `+${n}` : `${n}`)

export const ROMAN = ['', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX']

/** The colour of an effect chip. */
export const TONE: Record<EffectPreset['tone'], string> = { good: 'var(--good)', bad: 'var(--bad)', gold: 'var(--gold)' }
