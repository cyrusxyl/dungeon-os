import { FitAddon } from '@xterm/addon-fit'
import { Terminal } from '@xterm/xterm'
import '@xterm/xterm/css/xterm.css'
import { useEffect, useRef, useState } from 'react'

import { wsPtyUrl } from '@/lib/stage'

/** The DM's raw terminal. Mounted only while the drawer is open. */
function Xterm() {
  const host = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const term = new Terminal({
      fontFamily: 'ui-monospace, Menlo, Consolas, monospace',
      fontSize: 13,
      theme: { background: '#14121c', foreground: '#ece6d6', cursor: '#c9a96e' },
      scrollback: 5000,
    })
    const fit = new FitAddon()
    term.loadAddon(fit)
    term.open(host.current!)
    const ws = new WebSocket(wsPtyUrl())
    ws.binaryType = 'arraybuffer'
    const sendSize = () => {
      fit.fit()
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'resize', rows: term.rows, cols: term.cols }))
    }
    ws.onopen = sendSize
    ws.onmessage = (m) => term.write(new Uint8Array(m.data as ArrayBuffer))
    const input = term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'input', data }))
    })
    const ro = new ResizeObserver(sendSize)
    ro.observe(host.current!)
    term.focus()
    return () => {
      ro.disconnect()
      input.dispose()
      ws.close()
      term.dispose()
    }
  }, [])
  return <div ref={host} className="h-full w-full" />
}

export function ConsoleDrawer({ open, onClose, dmLog }: { open: boolean; onClose: () => void; dmLog: string[] }) {
  const [tab, setTab] = useState<'terminal' | 'log'>('terminal')
  if (!open) return null
  return (
    <div className="fixed inset-x-0 bottom-0 z-40 flex h-[60vh] flex-col border-t-4 border-[var(--gold)] bg-[var(--ink)]">
      <div className="flex items-center gap-2 border-b-2 border-[var(--border)] px-3 py-2">
        {(['terminal', 'log'] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`pixel-font px-2 py-1 text-[10px] ${tab === t ? 'bg-[var(--gold)] text-[var(--ink)]' : 'text-[var(--dim)] hover:text-[var(--parchment)]'}`}
          >
            {t === 'terminal' ? 'DM terminal' : 'DM notes'}
          </button>
        ))}
        <span className="ml-2 hidden text-sm text-[var(--dim)] sm:inline">
          Behind the screen. Tool output here can include DM-only notes.
        </span>
        <button type="button" onClick={onClose} className="pixel-font ml-auto px-2 py-1 text-[10px] text-[var(--dim)] hover:text-[var(--parchment)]">
          Close ✕
        </button>
      </div>
      <div className="min-h-0 flex-1 p-2">
        {tab === 'terminal' ? (
          <Xterm />
        ) : (
          <div className="h-full overflow-y-auto pr-2 font-mono text-sm whitespace-pre-wrap text-[var(--dim)]">
            {dmLog.length ? dmLog.map((t, i) => <p key={i} className="mb-3 border-l-2 border-[var(--border)] pl-3">{t}</p>) : 'No DM notes yet.'}
          </div>
        )}
      </div>
    </div>
  )
}
