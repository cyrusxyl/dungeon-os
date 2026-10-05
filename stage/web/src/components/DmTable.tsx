import { useEffect, useState } from 'react'

const FLAVOUR = ['Shuffling the notes', 'Sharpening quills', 'Consulting the dice', 'Warming up the voices']
const SHOWN = 2
// The DM paces the floor in front of the table; x is the left edge of its 64 px frame.
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
      className="absolute top-[92px] h-[64px] w-[64px] transition-[left] duration-[2200ms] ease-linear motion-reduce:transition-none"
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

const SPARKS = [
  { x: 128, d: '0s' },
  { x: 152, d: '0.9s' },
  { x: 176, d: '1.8s' },
  { x: 196, d: '0.4s' },
]

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
      <img src="/asset/filler.png" alt="" draggable={false} className="pixelated absolute inset-0 h-full w-full" />
      {SPARKS.map((s) => (
        <span key={s.x} className="dm-scribble absolute top-[70px] h-[2px] w-[6px] bg-[var(--gold)] opacity-0" style={{ left: s.x, animationDelay: s.d }} />
      ))}
      <div className="dm-flutter absolute left-[124px] top-[78px] h-[6px] w-[12px] bg-[var(--parchment)]" style={{ ['--r' as string]: '-8deg' }} />
      <div className="dm-flutter absolute left-[140px] top-[84px] h-[5px] w-[10px] bg-[#d8c9a0]" style={{ ['--r' as string]: '6deg', animationDelay: '0.4s' }} />
      <div className="dm-roll absolute left-[172px] top-[88px] size-[4px] bg-white" />
      <div className="dm-roll absolute left-[182px] top-[90px] size-[3px] bg-[var(--ember)]" style={{ animationDelay: '0.7s' }} />
      <div className="absolute left-[196px] top-[80px] h-[8px] w-[4px] bg-[var(--parchment)]" />
      <div className="dm-flame absolute left-[197px] top-[75px] h-[5px] w-[2px] bg-[var(--ember)]" />
      <Dm x={x} facing={facing} />
      <div className="pixel-font absolute inset-x-0 bottom-0 flex h-[40px] flex-col justify-end gap-[2px] border-t-2 border-[var(--border)] bg-[var(--panel)]/90 px-3 pb-[5px]">
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
