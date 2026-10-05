# Character creation screen

## Problem

Review of the first `the-underdark` session (Haiku DM, 2026-10-04):

1. The DM built the world (story bible, canon, scene, map). This took minutes. The player had nothing to do.
2. The DM then showed an opening scene to a party with no characters.
3. When the player asked for character creation, the DM asked for a player name in its chat reply. The stage does not show the chat reply, so the player did not see the question.

Cause: `AGENTS.md` Session Start says "greet players" and "ask What do you do?". Nothing tells the DM that a campaign with no sheets needs characters first. Character creation by chat also costs many DM turns.

## Solution

A character creation screen in the web UI. The server builds the sheet with `creation.create()` (no DM turn). While the player uses the screen, the DM builds the world in the background.

### Flow: new campaign, the player makes the party (default)

1. Menu > New Game: campaign name, optional pitch (free text), and "Who makes the party": **I make my characters** (default) or **The DM makes them from the pitch**.
2. The server writes `pitch` and `party` (`"create"` or `"premade"`) into `config.json`, then starts the DM.
3. The first DM prompt (chosen from the files, see below) tells the DM: build the world, show no beat, make no characters, do not ask for a player name. End the turn with "World ready."
4. The game view shows the creator (snapshot `creating: true`). A banner shows the DM status ("The DM is building the world…", then "The world is ready").
5. The player submits a character. The server writes the sheet, the player file, the party entry and the stage look. The player can make more characters.
6. The player clicks **Begin adventure**. The server queues one prompt that names the new character ids. The server types the prompt into the DM terminal when the DM is idle (after worldbuilding, if it still runs).
7. The DM reads the sheets, weaves the hooks into `dm_story.md`, and opens the first scene with the party on stage.

### Flow: preset characters (for example a BG3 epilogue)

The player picks "The DM makes them from the pitch". The first prompt tells the DM to build the world, then make each character with `character new` (level 1) and `level-up` to the level the pitch implies (with `--asi` on ASI levels), set the looks, then open the first scene. The game view shows the normal stage with a waiting status. No creator.

### Flow: a new player joins a running campaign

The **New character** button (party panel) opens the creator. On **Begin adventure** (label: **Join the party**), the queued prompt names the new ids, tells the DM to level them to the party level, and to bring them into the story at a fitting moment.

### First prompt: chosen from the files, not from the button

`stage_first_prompt(campaign_dir)` serves New Game, Load, Resume and Restart. Rules, in order:

1. No `dm_story.md` (an `exists()` check; the server never reads it): **new world** prompt. If `party` is `"premade"`: add the preset instructions and the pitch. Else: add "the player is on the creation screen".
2. No character sheets and `party` is not `"premade"`: **waiting for characters** prompt: "The world exists. The player is on the creation screen. Show no beat. Wait."
3. Else: the current prompt.

`creating` in the snapshot: set once when the stage starts, from the files (no sheets and `party` != `"premade"`), and by **New character**. Only `/api/creation/done` clears it. The first sheet does not close the creator. A browser reload keeps it; a server restart derives it again from the files.

## API contract

All POST bodies are JSON. An error is HTTP 400 (or 409 if no game runs) with `{"error": "<text>"}`.

### `POST /api/game/start` (changed)

Request: `{"new_name": "The Sunless Citadel", "pitch": "optional text", "party": "create" | "premade"}` or `{"campaign": "<slug>"}`.
`pitch` and `party` apply only with `new_name`. Default `party` is `"create"`. `party: "premade"` with an empty pitch is a 400 error.

### Snapshot (changed)

`{"kind": "snapshot", "state": {..., "creating": bool, "party_mode": "create" | "premade"}, "campaign": "<slug>"}`

### `GET /api/creation/options`

Built from the 5e API (cached on disk by `api_get`, memoized in the server, prefetched in a background thread when a game starts). Slow on a cold cache. If the API cannot be reached: 503 `{"error": "The 5e rules API cannot be reached. Check the network and try again."}`.

```json
{
  "races": [
    {"index": "elf", "name": "Elf", "speed": 30,
     "ability_bonuses": {"dexterity": 2},
     "bonus_choice": null,
     "subraces": [{"index": "high-elf", "name": "High Elf", "ability_bonuses": {"intelligence": 1}}],
     "look_race": "elf"}
  ],
  "classes": [
    {"index": "wizard", "name": "Wizard", "hit_die": 6,
     "saves": ["intelligence", "wisdom"],
     "skill_count": 2, "skill_options": ["arcana", "history", "insight"],
     "spellcasting": {"ability": "intelligence", "cantrips": 3, "spells": 6,
                      "cantrip_options": [{"index": "fire-bolt", "name": "Fire Bolt"}],
                      "spell_options": [{"index": "magic-missile", "name": "Magic Missile"}]},
     "equipment": {"fixed": [{"index": "spellbook", "name": "Spellbook", "quantity": 1}],
                   "choices": [{"label": "a quarterstaff or a dagger",
                                "options": [{"index": "quarterstaff", "name": "Quarterstaff"},
                                            {"index": "dagger", "name": "Dagger"}]}]}}
  ],
  "backgrounds": [{"index": "acolyte", "name": "Acolyte", "skills": ["insight", "religion"]}],
  "skills": ["acrobatics", "animal_handling", "...all keys of combat.SKILLS"],
  "abilities": ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"],
  "look": {
    "bodies": ["male", "female", "muscular"],
    "eyes": ["blue", "green", "..."],
    "races": {"elf": {"skins": ["light", "..."], "default_skin": "light"}, "drow": {"skins": ["blue", "black", "lavender"], "default_skin": "blue"}},
    "hair": [{"id": "hair_long", "name": "Long"}],
    "hair_colors": ["blonde", "dark_brown", "white", "..."]
  }
}
```

Notes:
- `bonus_choice`: `null`, or `{"count": 2, "options": ["strength", ...]}` (half-elf).
- `skill_options` and background `skills` use `combat.SKILLS` keys (`animal_handling`, not `skill-animal-handling`).
- `spellcasting` is `null` for a class with no spells at level 1. `spells` is the number to pick at level 1: `spells_known` if the level data has it; wizard 6 (spellbook); a prepared caster (cleric, druid): 0 here, the client shows "you prepare spells each day; pick up to ability mod + 1". `spell_options` are the class spells of level 1, `cantrip_options` level 0.
- `equipment.choices`: only choices whose options are plain equipment references. Skip the rest (the DM can add gear later).
- The SRD has one background (Acolyte). The client also offers **Custom background**: a name and two skills (`background_skills`).
- The SRD has no drow subrace. `look_race` maps the sheet race to a look race in `stage/data/races.json`. The appearance step lets the player pick any look race (for example "drow" for an Elf).

### `GET /asset/look.png?race=elf&body=female&skin=light&eyes=green&hair=hair_long:blonde&class=wizard`

A portrait PNG of a look that is not saved. Same build path as `actor set` (no save, no notify). 404 if the art cannot be made.

### `POST /api/creation/character`

Request:

```json
{
  "player_name": "Cyrus",
  "name": "Lyra Moonwhisper",
  "race": "elf", "subrace": "high-elf",
  "class": "wizard",
  "background": "acolyte", "background_skills": [],
  "scores": [8, 14, 13, 15, 10, 12], "assign": ["str", "dex", "con", "int", "wis", "cha"],
  "bonus_abilities": [],
  "skills": ["arcana", "history"],
  "cantrips": ["fire-bolt", "light", "mage-hand"], "spells": ["magic-missile", "shield"],
  "equipment": ["quarterstaff", "spellbook"],
  "alignment": "Neutral Good",
  "personality_traits": "text", "ideals": "text", "bonds": "text", "flaws": "text",
  "backstory": "text",
  "hooks": {"past": "people or places to see again", "problem": "an unfinished problem"},
  "look": {"race": "elf", "body": "female", "skin": "light", "eyes": "green", "hair": "hair_long:blonde"}
}
```

The server: id = slug of `name` (add `-2`, `-3` if taken); player id = slug of `player_name`. Call `creation.create(campaign_dir, rules_cmd._api, ...)`. Then add `personality_traits`, `ideals`, `bonds`, `flaws` (strings), `backstory` (string) and `hooks` to the sheet. Then save the look with the shared look function (the sheet must exist first). Nothing is written when `create` fails.

Response: `{"id": "lyra-moonwhisper", "lines": ["Lyra Moonwhisper: Elf (High Elf) Wizard 1 ..."]}`. Error: 400 `{"error": "<RulesError text>"}`.

### `POST /api/creation/open`

Sets `creating: true` (New character button). Response `{"ok": true}`.

### `POST /api/creation/done`

Request: `{}`. Sets `creating: false`. Queues one DM prompt that names every character made since the creator opened, then returns `{"ok": true}`. With no new characters: `creating: false`, no prompt (Cancel).

The queue: `Stage.pending: list[str]`. `Stage.tail()` sends the first prompt with `submit()` when the DM status is `idle`. One paragraph per prompt (`submit` joins whitespace).

## Code changes

Backend (`stage/server.py`, `dnd_cli/creation.py`, `dnd_cli/campaign.py`, `dnd_cli/commands/actor_cmd.py`, `stage/actors.py`, tests):
- `create_campaign(name, pitch, party)` writes the config fields.
- `creation.options(fetch)` builds the options document. Stub-fetch tests.
- Extract the body of `actor_cmd.execute_set` into one shared look function (build, normalize, validate, sex_fixed, save, notify). The CLI and the server both call it. An explicit `race=` token wins over the sheet race.
- Routes, queue, `creating`, first prompts, prefetch.
- Server docstring allowlist: the server now also writes `characters/`, `players/`, `state.json` (via `creation.register`), `stage/actors/`, and reads `config.json`.

Frontend (`stage/web/src`):
- `Menu.tsx`: pitch textarea and party mode.
- `CharacterCreator.tsx`: steps Who → Race → Class → Background → Abilities → Skills → Spells (casters) → Gear → Look → Story → Review. DM status banner. After create: "Make another" or "Begin adventure".
- `GameView.tsx`: show the creator when `creating`. A **New character** button in the party panel area.

Skills and docs (`game/AGENTS.md`, `game/.claude/skills/character-creation`, `stage`, `worldbuilding`, `README.md`):
- AGENTS.md Session Start: with no sheets, do not greet, show no beat, do not ask for a player name.
- character-creation skill: on the stage, never run the question workflow. Point the player to the **New character** button. The chat workflow stays for `--classic`.
- worldbuilding: Player-Specific Hooks come from the sheet `hooks` and `backstory`.
