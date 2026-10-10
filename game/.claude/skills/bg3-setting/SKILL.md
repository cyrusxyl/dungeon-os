---
name: BG3 Setting
description: Baldur's Gate 3 world background for the DM — the city and its districts, the gods (the Dead Three, Shar, Selûne, Mystra), the factions, the Absolute and the Netherstones, and a timeline with each fact tagged by era. Load when a scene, NPC, location or rumor needs Baldur's Gate lore, or when a player asks what the world knows about the Absolute, the Cult of Bhaal, mind flayers or the Dead Three.
---

# BG3 Setting

This skill is a lore shelf. It is not a rules source and not a plot. 5e rules come from `dnd-cli`.

## Precedence
1. `canon.json` (what happened at the table)
2. `dm_story.md` (what this campaign intends)
3. This skill (source lore)

If the campaign departs from the source, the campaign is right. Do not "fix" it back. The Sunless Citadel campaign says it departs from its source.

## Era tags
Every fact in `references/setting.md` has an era tag. Check the tag before you use the fact.
- `[old]` true in every era.
- `[1480s]` the years before the game. Cazador, the Bhaalist cult, and the Gortash and Thorm schemes are young or hidden.
- `[1492]` the game year. Mind flayer ships, the tadpole plague, the Absolute's army. Not true in the 1480s.
- `[after]` the epilogue. True only if the campaign picks it.

Do not put a `[1492]` fact in a `[1480s]` scene. Players must not learn it by accident.

## How to use it
- Give lore through people, rumors and objects. Do not read it out.
- Keep any `DM-ONLY` line out of narration. Use the three-clue rule (`dm-craft-principles`) to leak it.
- A new NPC, place or quest: hand off to `worldbuilding`. A talk scene: `social`. A picture: `stage`.
- Write all lore in your own words in narration. Do not copy wiki text.
- BG3 house rules (free smites, open multiclassing, the one human type, flexible +2/+1) are opt-in. Use them only if `config.json` or `dm_story.md` says so. 5e stays the rules authority.

## Read next
`references/setting.md` for the city, gods, factions and timeline.
