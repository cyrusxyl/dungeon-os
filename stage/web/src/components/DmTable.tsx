import { useEffect, useState } from 'react'

const FLAVOUR = ['Shuffling the notes', 'Sharpening quills', 'Consulting the dice', 'Warming up the voices']
const SHOWN = 5

function useFlavour(on: boolean): string {
  const [i, setI] = useState(0)
  useEffect(() => {
    if (!on) return
    const t = setInterval(() => setI((n) => (n + 1) % FLAVOUR.length), 2500)
    return () => clearInterval(t)
  }, [on])
  return FLAVOUR[i]
}

function Dm() {
  const [failed, setFailed] = useState(false)
  if (failed)
    return (
      <svg viewBox="0 0 64 64" className="h-full w-full" aria-hidden="true">
        <circle cx="32" cy="22" r="8" fill="#3a3350" />
        <rect x="22" y="31" width="20" height="26" rx="3" fill="#3a3350" />
      </svg>
    )
  return <img src="/asset/actor/wizard/full.png?f=right" alt="" draggable={false} className="pixelated h-full w-full" onError={() => setFailed(true)} />
}

const SCRIBBLES = [
  { x: 112, d: '0s' },
  { x: 150, d: '0.9s' },
  { x: 188, d: '1.8s' },
  { x: 214, d: '0.4s' },
]

// The DM at work: shown in place of the stage while there is no scene yet.
export function DmTable({ activity }: { activity?: string[] }) {
  const list = activity ?? []
  const flavour = useFlavour(list.length === 0)
  const current = list.at(-1) ?? flavour
  const done = list.slice(-SHOWN - 1, -1)

  return (
    <div className="absolute inset-0 overflow-hidden" role="status" aria-live="polite">
      <div className="absolute inset-x-0 top-0 h-[112px]" style={{ background: 'linear-gradient(#171322 0 70%, #1d1829 70% 100%)' }} />
      {SCRIBBLES.map((s) => (
        <span key={s.x} className="dm-scribble absolute top-[70px] h-[2px] w-[6px] bg-[var(--gold)] opacity-0" style={{ left: s.x, animationDelay: s.d }} />
      ))}
      <div className="dm-lean absolute left-[128px] top-[10px] h-[64px] w-[64px]">
        <div className="dm-bob h-full w-full">
          <Dm />
        </div>
      </div>
      <div className="absolute left-[64px] top-[66px] h-[8px] w-[192px] bg-[#5a3d26]" />
      <div className="absolute left-[72px] top-[74px] h-[30px] w-[176px] bg-[#3e2a1a]" />
      <div className="dm-flutter absolute left-[96px] top-[60px] h-[6px] w-[12px] bg-[var(--parchment)]" style={{ ['--r' as string]: '-8deg' }} />
      <div className="dm-flutter absolute left-[110px] top-[61px] h-[5px] w-[10px] bg-[#d8c9a0]" style={{ ['--r' as string]: '6deg', animationDelay: '0.4s' }} />
      <div className="dm-roll absolute left-[196px] top-[62px] size-[4px] bg-white" />
      <div className="dm-roll absolute left-[206px] top-[63px] size-[3px] bg-[var(--ember)]" style={{ animationDelay: '0.7s' }} />
      <div className="absolute left-[228px] top-[58px] h-[8px] w-[4px] bg-[var(--parchment)]" />
      <div className="dm-flame absolute left-[229px] top-[53px] h-[5px] w-[2px] bg-[var(--ember)]" />
      <div className="absolute inset-x-0 bottom-0 flex h-[80px] flex-col justify-end gap-[3px] border-t-2 border-[var(--border)] bg-[var(--panel)] px-3 pb-2 pixel-font">
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
