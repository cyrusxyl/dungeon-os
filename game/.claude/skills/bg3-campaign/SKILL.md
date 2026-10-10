---
name: BG3 Campaign
description: Turn Baldur's Gate 3 material into a playable DungeonOS campaign — pick an era (before the game, during it, or the epilogue), seed dm_story.md, add villains and clocks, and hand off to the other skills. Load when the host asks for a BG3-based or Baldur's Gate campaign, a retelling of the game, or when dm_story.md for a BG3 campaign must be written or revised.
---

# BG3 Campaign

This skill is a planner. The other skills do the work. Precedence: `canon.json` > `dm_story.md` > `bg3-*` skills.

## Step 1: choose the era (ask the host with AskUserQuestion)
| Era | Fits | Warning |
|---|---|---|
| `[1480s]` before the game | Slow intrigue, one villain, small cast. Matches the Sunless Citadel campaign. | Game plot is not true yet. |
| `[1492]` during the game | The tadpole plague and the Absolute. Large scale. | The party is not the game's hero. Decide the new hero's role. |
| `[after]` the epilogue | Fame, hunted heroes, old companions, fallout. | Needs a stated ending. Ask which one. |

## Step 2: write `dm_story.md`
Follow `worldbuilding` ("Campaign Story Bible"). Use `bg3-setting` for facts and `bg3-cast` for people. Mark secrets DM-ONLY. State at the top which source facts the campaign changes.

## Step 3: enter villains and clocks
Use the commands in `worldbuilding` (`canon add-villain`, `canon add-clock`). Clocks have 4, 6 or 8 segments. Do not hand-edit `canon.json`.

## Step 4: build the party
New player characters: the creation screen (`character-creation`). Existing BG3 characters: `bg3-cast` and the blocker note there.

## Step 5: encounters
SRD monsters come from `dnd-cli`. Hand-written: `mind-flayer`, `intellect-devourer`, `githyanki-warrior` (in `dnd_cli/data/overrides/monsters/`). Add more there in the same JSON shape, or reskin an SRD monster (for example an owlbear for a hulking horror) and say so in canon.

## Step 6: opt-in house rules
Free smites, open multiclassing, one human type, flexible +2/+1 bonus. Add to `config.json` notes only if the host agrees. 5e stays the default.

## Spoilers
Keep game-plot reveals out of player-facing text until the party earns them in play.
