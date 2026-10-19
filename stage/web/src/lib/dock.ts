// The roll strip of a fight: the board mounts an element under itself, and the roll window draws there instead of over the scene.
import { useSyncExternalStore } from 'react'

let el: HTMLElement | null = null
const listeners = new Set<() => void>()

/** The board calls this with its strip element when it mounts, and with null when it goes. */
export function setDock(next: HTMLElement | null): void {
  if (next === el) return
  el = next
  listeners.forEach((l) => l())
}

export const useDock = (): HTMLElement | null =>
  useSyncExternalStore(
    (l) => {
      listeners.add(l)
      return () => void listeners.delete(l)
    },
    () => el,
  )
