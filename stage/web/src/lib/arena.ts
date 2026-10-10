// The board of a fight: what GET /api/arena/<id> returns (stage/board.py `view`).
import type { Health } from '@/lib/party'

export type Cell = [number, number]

export interface ArenaUnit {
  id: string
  name: string
  x: number
  y: number
  pc: boolean
  down: boolean
  health: Health
  conditions: string[]
  /** Only a player character shows numbers. */
  hp?: { current: number; max: number }
  /** What a creature will do on its turn (a creature the stage plays; the DM's creatures say "DM decides"). */
  intent?: { kind: string; text: string }
}

export interface ArenaView {
  id: string
  w: number
  h: number
  /** `#` wall, `.` floor, `d` door gap, `~` hazard, ` ` a cell never seen (dim or dark light). */
  grid: string[]
  /** The cells in sight now (`1`), in dim or dark light; null in a lit room. */
  visible: string[] | null
  light: 'lit' | 'dim' | 'dark'
  hazard: 'lava' | 'water'
  tiles: { walls: number; floors: number; pattern: boolean }
  props: { id: string; kind: string; x: number; y: number }[]
  items: { id: string; name: string; x: number; y: number }[]
  units: ArenaUnit[]
  current: string | null
  round: number
  /** Where the character whose turn it is can walk now. */
  walk: Cell[]
  feet_left: number
  /** A player is asked whether to take a reaction attack. */
  pending: { who: string; against: string; seconds_left: number | null } | null
  settings: { reaction_seconds: number; round_summary: boolean }
}

/** One thing a character can do now: GET /api/arena/hand (stage/hand.py `listing`). `why` is the reason it is off, or null. */
export interface Ability {
  id: string
  name: string
  cost: 'action' | 'bonus' | 'reaction' | 'free'
  kind: string
  icon: string
  text: string
  stat: string
  why: string | null
  /** What the player must give: a target from the list, a cell for an area, words for the DM (Improvise), or nothing. */
  needs: 'target' | 'aim' | 'text' | 'none'
  targets?: { id: string; name: string; dist_ft: number; ok: boolean; why: string | null; odds?: string }[]
  shape?: { type: string; size_ft: number; range_ft: number }
  /** `item` for a row of the inventory (the Items drawer), `board` for an object on a tile. */
  source?: string
  qty?: number
}

export interface HandView {
  who: string
  abilities: Ability[]
  turn: { action: boolean; bonus: boolean; reaction: boolean }
  feet_left: number
  current: string | null
}

/** The cells and creatures an area would cover: POST /api/arena/preview. */
export interface Preview {
  ok: boolean
  why: string | null
  cells: Cell[]
  units: string[]
  /** The cell this preview was asked for (set by the browser). */
  at?: Cell
}
