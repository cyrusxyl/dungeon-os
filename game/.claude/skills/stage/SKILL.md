---
name: stage
description: Show the game to the players on the pixel-art visual stage — scenes, characters entering and leaving, narration, NPC dialogue with portraits and emotions, and choice buttons — with one `uv run dnd-cli show beat` call per reply; set how characters look with `dnd-cli actor set` and how places look with `dnd-cli scene set`; put places on the region and city map with `dnd-cli map place`; make dungeons and buildings the players walk through with `dnd-cli site set` and `@explore`. Use for every reply when the session prompt says the players watch the visual stage.
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
| `@explore <site-id> [<poi-id>\|entrance]` | Show a site the players walk through (see Sites). |

A line with no `@` continues the line before it.

## Ids

- **Location id**: the location file name without extension (`world/locations/stonehill-inn.md` → `stonehill-inn`), or a new short slug in lower case with `-`.
- **Actor id**: the character file name (`characters/sireth.json` → `sireth`) or NPC file name (`world/npcs/cassara-whitmore.json` → `cassara-whitmore`).
- **Several monsters of one kind**: `goblin#1`, `goblin#2`.
- Ids use lower-case letters, digits, `-` and `_` only.

A character speaking with `@say` is put on stage if it is not there yet. A warning "no appearance for ..." is not an error: the stage shows a silhouette.

## Characters: how they look

Each actor shows as a Universal LPC pixel sprite, with a portrait cut from it. Looks are saved in the campaign and reused in every later session. Do not check or redo them. **Set a look only when `show beat` warns** "no appearance for ..." (the stage showed a silhouette). The stage swaps the silhouette for the new picture by itself; there is no need to send the beat again.

```bash
uv run dnd-cli actor set cassara-whitmore name=Cassara_Whitmore body=female skin=light eyes=green hair_bob:chestnut blouse_longsleeve:white corset:maroon skirt_straight:black shoes_basic:black
```

- `name=` is the name on the dialogue box (use `_` for spaces). `body=` is `male`, `female`, `muscular`, `teen`, `pregnant`, or `child`.
- `skin=`: `light`, `amber`, `olive`, `taupe`, `bronze`, `brown`, `black` for human tones; `blue`, `lavender`, `green`, `pale_green`, `dark_green`, `bright_green`, `zombie`, `fur_*` for others. `eyes=`: `blue`, `green`, `brown`, `gray`, `red`, `orange`, `yellow`, `purple`.
- **One `set` per Bash call, on one line.** Do not chain with `&&` and never break a line with `\`: a backslash line break always stops for a permission prompt, and the first error in a chain stops the rest.
- Every other word is an item, optionally with a color: `robe:white`. Names of the head, ears, hair, clothes, legs, shoes, hats, weapons and more: `uv run dnd-cli actor options` (types) and `uv run dnd-cli actor options <type> --body female` (items and colors that fit).
- Start from a kind with `preset=guard` and change pieces: `uv run dnd-cli actor set captain-voss preset=guard name=Captain_Voss hair_buzzcut:black`. Presets: goblin, hobgoblin, orc, troll, skeleton, zombie, vampire, kobold, lizardfolk, gnoll, werewolf, minotaur, bandit, thug, guard, knight, cultist, commoner, merchant, noble, priest, wizard, sailor.
- **Race:** `race=drow` (or `elf`, `half-elf`, `dwarf`, `halfling`, `gnome`, `half-orc`, `orc`, `dragonborn`, `tiefling`, `human`) adds the ears, horns, tail, head, body and skin of that race; your own `body=`, `skin=`, `eyes=` and items win. A player character with a sheet gets its race from the sheet by itself.
  The `child` body fits only a few items. Use `teen` for small folk.
- A saved look is final. `actor set` on an id that has a look does nothing and prints the saved look. Add `--change` only when the story changes the look (a disguise, a wound, new armor); it changes only the pieces you give. Never change a player character's look unless that player asks.
- A warning "has no sprite for body ..." means the item will not show on that body. Pick an item the warning says fits.
- Unnamed monsters need nothing: `goblin#1` and `goblin#2` use the `goblin` preset. A beast with no preset (`wolf#1`, `rat#2`) finds a matching monster tile by its name.
- For a beast or monster LPC has no body for, use a monster tile: `uv run dnd-cli actor set the-beast name=The_Beast tile=bear`. The command prints the tile it picked.
- Look from the players' side: a disguised NPC wears the disguise. Use what the players can see, never the secret.
- To check a look: `uv run dnd-cli actor preview <id>` writes a PNG you can read. Use it once for an important character, not every turn.
- Player characters need a look too. If a character file has none, make one from the sheet (race, class, gear), and ask the player in a beat if a detail matters to them.

## Places: how they look

Each location shows as a room or outdoor place built from LPC tiles. Places are saved in the campaign and reused on every visit. **Set a place only when `show beat` warns** "no look for location ..." (the stage showed a blank room). The room appears by itself. The location id in `scene set` and in `@scene` must be the same. For a new place you know you will show, you can set it before the beat.

```bash
uv run dnd-cli scene set chapel-of-ilmater template=chapel mood=dusk wall_center=bust +plant@front_left
```

- `template=` sets the whole place: `chapel`, `temple`, `tavern`, `shop`, `house`, `hall`, `cellar`, `dungeon`, `cave`, `street`, `dock`, `forest`, `road`, `swamp`, `beach`. Pick the closest one.
- Change it only where the story needs it:
  - `wall=` and `floor=` change the materials (`wall=brick_red`, `floor=planks_dark`).
  - `mood=` sets the light: `day`, `dusk`, `night`, `torchlit`, `fog`, `rain`.
  - `<slot>=<prop>` replaces what stands in a slot, and `<slot>=none` empties it. Wall slots: `wall_left`, `wall_left2`, `wall_center`, `wall_right2`, `wall_right`. Floor slots: `back_left` … `front_right` (back, mid, front × left, center, right).
  - `+<prop>@<zone>` adds an extra prop in a floor zone; the composer finds the spot. `clear=add` removes the extras.
- Lists of templates, walls, floors, props and moods: `uv run dnd-cli scene options` (or `scene options props`).
- A saved place is final. `scene set` on a place that has a look does nothing and prints the saved look. Add `--change` only when the story changes the place ("the chapel burns": `--change mood=night back_center=none`); it changes only what you give. A revisit shows the same place.
- If no prop fits ("a statue of Ilmater"), the command suggests the closest props and records the gap. Use the closest prop and describe the difference in the story text.
- To check a place: `uv run dnd-cli scene preview <location-id>` writes a PNG you can read. Use it once for an important place.
- You never give pixel positions. Slots and zones are the only placement.

## Maps: region and city

The players open a map of the places they know. Looking costs you nothing. When they pick a place, you get a `[map]` message.

```bash
uv run dnd-cli map place sword-coast baldurs-gate "name=Baldur's Gate" icon=city
uv run dnd-cli map place sword-coast candlekeep from=baldurs-gate dir=n travel=2_days
uv run dnd-cli map place baldurs-gate chapel-of-ilmater in=sword-coast
uv run dnd-cli map place sword-coast cloakwood from=baldurs-gate dir=se travel=1_day hidden=yes
uv run dnd-cli map reveal sword-coast cloakwood
```

- Add a place when the players learn of it (a rumor, a map, a guide) or arrive. Not before: a place you add is on their map at once. To plan ahead, add it with `hidden=yes` and `map reveal` it later.
- The first place of a map needs nothing else. Every later place needs `from=` (a place on that map) and `dir=` (`n` `ne` `e` `se` `s` `sw` `w` `nw`); `travel=` is the time on that route. The stage does the layout.
- A city map is the inside of the region place with the same id: give `in=<region-map>` with the first place of the city map.
- **The place id is the location id.** `@scene chapel-of-ilmater` moves the party marker there and writes the location in `state.json` for you. A site's id is its place id too.
- Icons: `uv run dnd-cli map options`. Check the whole map, hidden places too: `uv run dnd-cli map show`.

## Sites: dungeons and buildings

A site is a generated floor plan that the players walk through by themselves. You set it once, with its points of interest (POI). The stage does the walking, the fog, and the wandering-monster checks, and calls you only when something happens.

```bash
uv run dnd-cli site set sunless-citadel name=Sunless_Citadel theme=crypt size=medium danger=low poi=dragon-altar@far poi=goblin-camp@mid:goblin poi=old-well@near:fountain
```

- `theme=`: `dungeon` `crypt` `castle` `sewer` `temple` `cave` (dungeons), `house` `tavern` `manor` (buildings). `size=`: `small` `medium` `large`. `danger=`: `none` `low` `mid` `high` (the chance of a wandering encounter in each new area).
- `poi=<id>@<where>[:<icon>]`. `where` is the walking distance from the entrance: `entrance` `near` `mid` `far` `any`. `icon` is an object (`altar` `chest` `stairs-down` `statue` `coffin` `trap` `treasure` ...) or an actor kind (`goblin`, `skeleton`, an actor id): the players see that sprite. List: `uv run dnd-cli site options`.
- A POI shows only when the players see it. Never put a secret in its id: they read the id as its name.
- A saved site is final. `site set <id> --change poi=...` adds POIs where the players have not looked yet; it can also change `name=` and `danger=`.
- `@explore <site-id>` shows the site; the party stands where it stood last (the entrance on the first visit). `@explore <site-id> <poi-id>` puts the party at a POI, for example the stairs of a floor below: a deeper floor is another site.
- In the site view, the players see the walls, doors and passages, and walk by themselves. **Do not describe the layout** (exits, passages, which way to go) and **do not give movement choices**. Narrate what they sense and what they find.
- For a fight or a talk, use `@scene` as usual (it leaves the site view), then send `@explore <site-id>` to let them walk on.

**Messages from the stage.** A message that starts with `[explore]` or `[map]` comes from the stage, not from a player's words. Do what it says in one beat:

- `the party sees <poi>`: show what they find (an `@narrate`, or a scene with actors).
- `wandering encounter check hit`: run an encounter that fits the place, or show that nothing comes.
- `examines <poi>`: show what a closer look gives.
- `leaves by the entrance`: show where they go next with `@scene`.
- `[map] The party travels ...`: run the journey (roll for encounters on the way), then show the arrival with the `@scene` it names.

## Rules

1. **Each reply is a beat.** Follow the Narration Budget in AGENTS.md: at most 3 sentences of narration, at most 2 sentences per NPC line, then a prompt to the player.
2. **Split long speech.** One `@say` is one dialogue-box page. Two short `@say` lines read better than one long one.
3. **Dice show on the stage by themselves.** Every roll of `attack`, `save`, `check`, and `uv run roll ...` appears as a dice box the players watch (`--secret` on the rules commands hides one). Still say what the roll means in the story text, for example `@narrate Your blade bites deep (18 vs AC 15) — 7 damage.` For a roll behind the DM screen (a hidden check, a secret DC), end the command with the shell comment `# secret`: `uv run roll 1d20+3 -v  # secret`. It then never reaches the stage.
4. **Use `@choices` to ask the players.** The AskUserQuestion tool is blocked on the stage. Give 2 to 4 short options. The player can still type anything. Session Zero and character creation work the same way: one question per beat, with `@choices` for a list (race, class, background) and free text for the rest. Do not put a long rules summary in a beat; give the short options and answer questions when the player asks.
5. **Never speak or act for a player character.** Never write an `@say` line for a PC, even when the player said what the character does: tell the action with `@narrate` ("Aragorn's longsword sings through the air…") and leave the words to the player. Do not decide what a PC does, says, or feels beyond what the player stated. Put PCs on stage with `@enter`, describe the world and the NPCs, then let the players answer with `@choices` or free text.
6. **Hidden information stays hidden.** A beat is shown to the players. Never put DM-only facts, villain plans, or clock counts in a beat. A disguised NPC uses an actor id and name the players know.
7. **Referee mode is a beat too.** A ruling is an `@narrate` line, short and plain (AGENTS.md rule 5).
8. **If the command fails**, read the error, fix the line it names, and send the beat again. Do not tell the story in chat instead.
