// Tile helpers shared by the crawl (sites) and the combat board (arenas).
import { useCallback, useRef, useState } from 'react'

/** Source tile size in pixels (DCSS and LPC tiles are 32 px). */
export const T = 32

/** A stable tile variant per cell; variant 0 about half of the time, like DCSS maps. Same as variant() in stage/arena.py. */
export function variant(x: number, y: number, n: number): number {
  const h = (Math.imul(x, 374761393) ^ Math.imul(y, 668265263)) >>> 0
  const k = ((h ^ (h >>> 13)) >>> 0) % (n * 2)
  return k < n ? k : 0
}

/** Images by URL; `tick` changes when one finishes loading, so the canvas redraws. */
export function useImages(): [(url: string) => HTMLImageElement | undefined, number] {
  const cache = useRef(new Map<string, HTMLImageElement>())
  const [tick, setTick] = useState(0)
  const get = useCallback((url: string) => {
    let img = cache.current.get(url)
    if (!img) {
      img = new Image()
      img.onload = () => setTick((t) => t + 1)
      img.src = url
      cache.current.set(url, img)
    }
    return img.complete && img.naturalWidth ? img : undefined
  }, [])
  return [get, tick]
}
