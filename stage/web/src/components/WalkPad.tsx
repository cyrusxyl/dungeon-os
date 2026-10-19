import type { Cell } from '@/lib/arena'

/** The 8 directions as the screen shows them: the grid is turned by 45 degrees, so "up" on the screen is one cell toward -x and -y. */
const DIRS: { label: string; d: Cell; rot: number }[] = [
  { label: 'up left', d: [-1, 0], rot: 315 },
  { label: 'up', d: [-1, -1], rot: 0 },
  { label: 'up right', d: [0, -1], rot: 45 },
  { label: 'left', d: [-1, 1], rot: 270 },
  { label: '', d: [0, 0], rot: 0 },
  { label: 'right', d: [1, -1], rot: 90 },
  { label: 'down left', d: [0, 1], rot: 225 },
  { label: 'down', d: [1, 1], rot: 180 },
  { label: 'down right', d: [1, 0], rot: 135 },
]

/** One step in any of 8 directions. A button is off when that step does not fit the feet left, or a wall or a creature is there. */
export function WalkPad({ at, walk, onStep }: { at: Cell; walk: Cell[]; onStep: (to: Cell) => void }) {
  const ok = new Set(walk.map(([x, y]) => `${x},${y}`))
  return (
    <div className="absolute bottom-2 left-2 grid grid-cols-3 gap-0.5 touch-manipulation" role="group" aria-label="Walk one step">
      {DIRS.map(({ label, d, rot }) => {
        if (!label) {
          return (
            <span key="mid" className="pixel-font grid size-10 place-items-center border-2 border-dashed border-[var(--border)] text-[7px] text-[var(--dim)]">
              WALK
            </span>
          )
        }
        const to: Cell = [at[0] + d[0], at[1] + d[1]]
        const on = ok.has(`${to[0]},${to[1]}`)
        return (
          <button
            key={label}
            type="button"
            disabled={!on}
            aria-label={`Walk ${label}`}
            title={d[0] && d[1] ? 'Straight: 5 ft' : 'Diagonal: 7 ft'}
            onClick={() => onStep(to)}
            className="grid size-10 place-items-center border-2 border-[var(--border)] bg-[var(--panel)]/90 active:border-[var(--gold)] active:bg-[var(--panel-2)] disabled:opacity-35"
          >
            <svg viewBox="0 0 20 20" className="size-5" style={{ transform: `rotate(${rot}deg)` }} aria-hidden="true">
              <polygon points="10,3 17,14 10,11 3,14" fill="var(--gold)" stroke="var(--ink)" strokeLinejoin="round" />
            </svg>
          </button>
        )
      })}
    </div>
  )
}
