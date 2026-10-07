import { type StageState, titleCase, useJson } from '@/lib/stage'

/** Where the party is, over the top of the scene. Put it in a `relative` box. */
export function SceneTitle({ state }: { state: StageState }) {
  const site = useJson<{ name?: string }>(state.explore ? `/api/site/${encodeURIComponent(state.explore)}` : null, state.versions?.[`site:${state.explore}`] ?? 0)
  const name = state.explore ? (site?.name ?? titleCase(state.explore)) : state.scene ? titleCase(state.scene) : ''
  if (!name) return null
  return (
    <h2 className="pixel-font pointer-events-none absolute inset-x-0 top-0 z-10 truncate bg-gradient-to-b from-black/80 to-transparent px-3 pt-2 pb-4 text-center text-[10px] text-[var(--gold)] sm:text-xs">
      {name}
    </h2>
  )
}
