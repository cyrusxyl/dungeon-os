import { useState } from 'react'

import { Button } from '@/components/ui/8bit/button'
import { Input } from '@/components/ui/8bit/input'
import type { Me } from '@/lib/seats'
import { postJson } from '@/lib/stage'

/** The host sees a code. Another device (the table screen) types it in to take over as the host. */
export function HostControls({ me }: { me: Me }) {
  const [open, setOpen] = useState(false)
  const [code, setCode] = useState('')
  const [bad, setBad] = useState(false)

  if (me.host) {
    return (
      <span className="text-sm text-[var(--dim)]" title="Type this code on another device to give it the host controls.">
        Host code <b className="pixel-font text-[10px] text-[var(--gold)]">{me.hostCode}</b>
      </span>
    )
  }
  if (!open) {
    return (
      <Button
        size="sm"
        variant="outline"
        onClick={() => setOpen(true)}
        title="Take over the host controls (Save, Quit, console). You need the host code from the host's screen."
        className="text-[10px]"
      >
        Take host
      </Button>
    )
  }
  return (
    <form
      className="flex items-center gap-2"
      onSubmit={async (e) => {
        e.preventDefault()
        const ok = (await postJson('/api/host/claim', { code })).ok
        setBad(!ok)
        if (ok) setOpen(false)
      }}
    >
      <Input aria-label="Host code" autoFocus value={code} onChange={(e) => setCode(e.target.value)} placeholder="Host code" font="normal" className="h-8 w-28 text-base" />
      <Button size="sm" type="submit" className="text-[10px]">
        Go
      </Button>
      <Button size="sm" type="button" variant="outline" onClick={() => setOpen(false)} className="text-[10px]">
        Cancel
      </Button>
      {bad && <span className="text-sm text-[var(--bad)]">Wrong code</span>}
    </form>
  )
}
