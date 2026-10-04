---
name: stage
description: Show the game to the players on the pixel-art visual stage — scenes, characters entering and leaving, narration, NPC dialogue with portraits and emotions, and choice buttons — with one `uv run dnd-cli show beat` call per reply. Use for every reply when the session prompt says the players watch the visual stage.
---

# Visual Stage

On the stage, the players do not read your chat reply. They see a pixel-art room, the characters in it, and a dialogue box. **Only what you send in a beat reaches them.**

## The one command

Send each reply as one beat, from your working directory, exactly in this form:

```bash
uv run dnd-cli show beat <<'EOF'
@scene chapel-of-ilmater
@enter sister-gareth right
@narrate Candle smoke hangs under the low beams.
@say sister-gareth happy What brings a drow monk to this particular chapel?
@choices Ask about the Fist | Show Cassara's note | Leave
EOF
```

- Do not put `cd ... &&` in front of it. A compound command needs a permission prompt; this form does not.
- Use one call per reply. Put every line of the reply in it, in the order the players must read them.
- Do mechanics (rolls, file reads, `dnd-cli character` and `canon` commands) first, then send the beat that tells the result.
- After the beat, end your turn with one short line such as "Beat shown." Your chat reply goes to the DM notes, not to the players. Do not repeat the story there.

## Beat lines

| Line | Effect |
|---|---|
| `@scene <location-id>` | Change the room. Clears the characters on stage. |
| `@enter <actor-id> [left\|center\|right\|far-left\|far-right]` | A character steps on stage. Position is optional. |
| `@exit <actor-id>` | A character leaves. |
| `@narrate <text>` | A narration line in the dialogue box, with no portrait. |
| `@say <actor-id> [emotion] <text>` | A character speaks, with portrait. Emotions: `neutral` `happy` `angry` `sad` `shock` `blush` `shame` `eyeroll` `closed`. |
| `@choices <a> \| <b> \| <c>` | Choice buttons. Put it last. The player can still type a free action. |
| `@clear` | Remove all characters, keep the room. |

A line with no `@` continues the line before it.

## Ids

- **Location id**: the location file name without extension (`world/locations/stonehill-inn.md` → `stonehill-inn`), or a new short slug in lower case with `-`.
- **Actor id**: the character file name (`characters/sireth.json` → `sireth`) or NPC file name (`world/npcs/cassara-whitmore.json` → `cassara-whitmore`).
- **Several monsters of one kind**: `goblin#1`, `goblin#2`.
- Ids use lower-case letters, digits, `-` and `_` only.

A character speaking with `@say` is put on stage if it is not there yet. A warning "no appearance for ..." is not an error: the stage shows a silhouette.

## Rules

1. **Each reply is a beat.** Follow the Narration Budget in AGENTS.md: at most 3 sentences of narration, at most 2 sentences per NPC line, then a prompt to the player.
2. **Split long speech.** One `@say` is one dialogue-box page. Two short `@say` lines read better than one long one.
3. **Show the result of a roll in the story text**, for example `@narrate Your blade bites deep (18 vs AC 15) — 7 damage.`
4. **Use `@choices` to ask the players.** The AskUserQuestion tool is blocked on the stage. Give 2 to 4 short options. The player can still type anything.
5. **Hidden information stays hidden.** A beat is shown to the players. Never put DM-only facts, villain plans, or clock counts in a beat. A disguised NPC uses an actor id and name the players know.
6. **Referee mode is a beat too.** A ruling is an `@narrate` line, short and plain (AGENTS.md rule 5).
7. **If the command fails**, read the error, fix the line it names, and send the beat again. Do not tell the story in chat instead.
