import { useCallback, useEffect, useState } from 'react'

import { GameView } from '@/components/GameView'
import { Menu, type MenuData } from '@/components/Menu'

/** The start menu when no game runs; the game view when one does. */
export default function App() {
  const [menu, setMenu] = useState<MenuData | null>(null)
  const [error, setError] = useState(false)

  const refresh = useCallback(() => {
    fetch('/api/menu')
      .then((r) => r.json())
      .then((d) => {
        setMenu(d)
        setError(false)
      })
      .catch(() => setError(true))
  }, [])

  useEffect(refresh, [refresh])

  if (error) {
    return <div className="pixel-font grid h-full place-items-center text-xs text-[var(--dim)]">The table server is not running.</div>
  }
  if (!menu) {
    return <div className="pixel-font grid h-full place-items-center text-xs text-[var(--dim)]">Setting the table…</div>
  }
  if (menu.game) {
    return <GameView key={menu.game} onMenu={refresh} />
  }
  return <Menu data={menu} onStarted={refresh} onChanged={setMenu} />
}
