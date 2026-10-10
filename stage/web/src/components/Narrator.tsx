import { type StoryLine } from '@/lib/stage'
import { useNarration, useVoiceOn } from '@/lib/voice'
import type { Mode } from '@/lib/view'

/** Plays the narration and speech for the current beat. It shows nothing. */
export function Narrator({ current, mode }: { current: StoryLine | undefined; mode: Mode }) {
  useNarration(current, useVoiceOn(mode))
  return null
}
