// The prop pictures of the isometric view: GET /api/props (rects and poses) and the one atlas picture they point into.
import { useEffect, useState } from 'react'

import type { PropEntry } from '@/lib/props'

export interface PropsInfo {
  atlas: string
  props: Record<string, PropEntry>
}

let pending: Promise<PropsInfo> | null = null

function load(): Promise<PropsInfo> {
  pending ??= fetch('/api/props')
    .then((r) => (r.ok ? (r.json() as Promise<PropsInfo>) : Promise.reject(new Error(String(r.status)))))
    .catch((e) => {
      pending = null // ask again next time
      throw e
    })
  return pending
}

/** The prop catalogue, or undefined until it has arrived. Fetched once for the whole page. */
export function usePropsInfo(): PropsInfo | undefined {
  const [info, setInfo] = useState<PropsInfo>()
  useEffect(() => {
    let live = true
    load().then((i) => live && setInfo(i), () => {})
    return () => {
      live = false
    }
  }, [])
  return info
}
