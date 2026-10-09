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
