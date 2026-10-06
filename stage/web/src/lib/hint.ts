import { useState } from 'react'

/** Button help: `tip(text)` gives a browser tooltip, and `hint` shows the text of the button under the pointer or focus (a phone has no hover). */
export function useHint() {
  const [hint, setHint] = useState('')
  const tip = (text: string) => ({
    title: text,
    onMouseEnter: () => setHint(text),
    onFocus: () => setHint(text),
    onMouseLeave: () => setHint(''),
    onBlur: () => setHint(''),
  })
  return { hint, tip }
}
