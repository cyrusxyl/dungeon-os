// This browser's small memory (localStorage). It is never required: a private window just forgets.

export function read(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

/** A saved JSON value, or `fallback` when there is none or it is damaged. */
export function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = read(key)
    return raw === null ? fallback : JSON.parse(raw)
  } catch {
    return fallback
  }
}

export function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* the choice lasts until the page closes */
  }
}
