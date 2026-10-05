import { useEffect, useState } from 'react'

const FLAVOUR = ['Shuffling the notes', 'Sharpening quills', 'Consulting the dice', 'Warming up the voices']
const SHOWN = 2
// The DM paces the floor in front of the desk; x is the left edge of its 64 px frame.
const PACE = [16, 64, 112, 168, 224, 168, 112, 64]

function useTick(ms: number): number {
  const [i, setI] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setI((n) => n + 1), ms)
    return () => clearInterval(t)
  }, [ms])
  return i
}

function Dm({ x, facing }: { x: number; facing: 'left' | 'right' }) {
  const [failed, setFailed] = useState(false)
  return (
    <div
      className="absolute top-[100px] h-[64px] w-[64px] transition-[left] duration-[2200ms] ease-linear motion-reduce:transition-none"
      style={{ left: x, filter: 'brightness(0.85) sepia(0.2)', transitionTimingFunction: 'steps(14)' }}
    >
      <div className="dm-bob h-full w-full">
        {failed ? (
          <svg viewBox="0 0 64 64" className="h-full w-full" aria-hidden="true">
            <circle cx="32" cy="22" r="8" fill="#3a3350" />
            <rect x="22" y="31" width="20" height="26" rx="3" fill="#3a3350" />
          </svg>
        ) : (
          <img src={`/asset/actor/wizard/full.png?f=${facing}`} alt="" draggable={false} className="pixelated h-full w-full" onError={() => setFailed(true)} />
        )}
      </div>
    </div>
  )
}

// The DM at work in its study: shown in place of the stage while there is no scene yet.
export function DmTable({ activity }: { activity?: string[] }) {
  const list = activity ?? []
  const step = useTick(2200)
  const x = PACE[step % PACE.length]
  // Moving right: the sprite looks right, which is the `left` pose.
  const facing = x >= PACE[(step + PACE.length - 1) % PACE.length] ? 'left' : 'right'
  const current = list.at(-1) ?? FLAVOUR[Math.floor(step / 1.2) % FLAVOUR.length]
  const done = list.slice(-SHOWN - 1, -1)

  return (
    <div className="absolute inset-0 overflow-hidden" role="status" aria-live="polite">
      <img src="/asset/filler.png?v=2" alt="" draggable={false} className="pixelated absolute inset-0 h-full w-full" />
      {/* Light only: the objects are baked into the room image. */}
      <div className="dm-glow absolute left-[126px] top-[2px] h-[52px] w-[68px]" />
      <div className="dm-glow absolute left-[178px] top-[92px] h-[44px] w-[44px]" style={{ animationDelay: '0.3s' }} />
      <Dm x={x} facing={facing} />
      <div className="pixel-font absolute inset-x-0 bottom-0 flex h-[38px] flex-col justify-end gap-[2px] border-t-2 border-[var(--border)] bg-[var(--panel)]/90 px-3 pb-[5px]">
        {done.map((label, i) => (
          <div key={`${label}-${i}`} className="truncate text-[6px] text-[var(--dim)] opacity-70">
            <span className="text-emerald-400">✓ </span>
            {label}
          </div>
        ))}
        <div className="truncate text-[8px] text-[var(--gold)]">
          {current}
          <span className="dm-dots" />
        </div>
      </div>
    </div>
  )
}
