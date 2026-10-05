/** A d20 with a number on its face. `tone` colours it: gold for a natural 20, red for a natural 1. */
export function D20({ value, tone = 'plain', className = '', glow }: { value: number | string; tone?: 'plain' | 'gold' | 'red'; className?: string; glow?: string }) {
  const fill = tone === 'gold' ? '#c9a96e' : tone === 'red' ? '#a33a3a' : '#3a3350'
  const facet = tone === 'gold' ? '#e2c88f' : tone === 'red' ? '#c55353' : '#4b4366'
  const ink = tone === 'gold' ? '#14121c' : '#ece6d6'
  return (
    <svg viewBox="0 0 100 100" className={className} style={glow ? ({ '--glow': glow } as React.CSSProperties) : undefined} aria-hidden="true">
      <polygon points="50,4 91,27 91,73 50,96 9,73 9,27" fill={fill} stroke="#14121c" strokeWidth="4" strokeLinejoin="round" />
      <polygon points="50,24 78,68 22,68" fill={facet} stroke="#14121c" strokeWidth="3" strokeLinejoin="round" />
      <g stroke="#14121c" strokeWidth="3" strokeLinecap="round">
        <line x1="50" y1="24" x2="9" y2="27" />
        <line x1="50" y1="24" x2="91" y2="27" />
        <line x1="78" y1="68" x2="91" y2="73" />
        <line x1="78" y1="68" x2="50" y2="96" />
        <line x1="22" y1="68" x2="9" y2="73" />
        <line x1="22" y1="68" x2="50" y2="96" />
        <line x1="50" y1="24" x2="50" y2="4" />
      </g>
      <text x="50" y="58" textAnchor="middle" fontSize={String(value).length > 1 ? 24 : 28} fontFamily="'Press Start 2P', monospace" fill={ink}>
        {value}
      </text>
    </svg>
  )
}
