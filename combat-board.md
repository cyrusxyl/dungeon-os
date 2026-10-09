# Combat Board

Design for fights on the visual stage. This file is a design only. Nothing here is built. The browser demo that shows it is a prototype of the look and the rules, not of the architecture (see rule 1).

Today a fight is a scene: the DM runs the rules with `dnd-cli encounter`, `attack` and `save`, and the stage shows dice and a party panel. There is no movement. The board adds movement, reach, sight and area effects, and it keeps the DM in control of the story.

| Part | What it is | Who decides |
|---|---|---|
| Arena | One room, built for the fight from the crawl room, the scene, or nothing | The stage; the DM edits it with words, not positions |
| Board | Tiles, speed, reach, line of sight, cover, hazards, reaction attacks | The engine |
| Player turn | Move, then pick an ability: card or list, on the phone or on the table | The player |
| Simple foes | Moves and abilities chosen by a score and a style | The engine |
| Named foes and bosses | The same, but the DM chooses | The DM |
| Improvised action | Anything the abilities do not cover | The player and the DM, with engine defaults |
| After the fight | XP, loot, return to the crawl or the scene | The engine rolls; the DM can force or change |

## Rules that apply everywhere

1. **The engine runs on the server.** Pathing, sight, foe turns, reactions and fog are Python in `stage/`, next to `crawl.py`. They call `dnd_cli/combat.py`. The browser draws only what the server sends. This keeps the crawl rule: hidden stays hidden. A foe in the dark is not in the data the browser gets.
2. **One rules core.** `combat.py` owns HP, rolls, initiative, conditions and XP. The board must call it. It must not copy it.
3. **One ability format.** A card, a list row, a foe action and a spell all use the same data (section 3). The skin is a choice of the player.
4. **The DM gives no positions.** The DM gives words (`cover@foes`, `layout=chokepoint`). The stage computes the layout. This is the same rule as the site command.
5. **The engine never refuses an improvised action.** It gives a default ruling or it asks the DM (section 6).
6. **Looking is free.** Moving, targeting preview and hover use no DM tokens. The DM is called only when a rule in this file says so.
7. **The DM stays in control.** The DM can take over any foe turn, change a ruling, or end the fight.

## 1. Starting a fight

### DM command

`encounter start` already takes `goblin:3` and `boss=bugbear`. The board adds one option:

```bash
uv run dnd-cli encounter start goblin:2 boss=bugbear --arena layout=pillars size=medium light=lit ambush=no feature=cover@foes hazard=lava@center
uv run dnd-cli encounter start goblin:3 --arena          # all defaults, from the source
```

- Without `--arena`, the fight runs as it does today. No board.
- `layout=` is `open`, `chokepoint`, `pillars` or `chasm`. The default comes from the source.
- `size=` is `small` (12 × 8) or `medium` (16 × 10).
- `light=` is `lit`, `dim` or `dark` (see Light).
- `ambush=yes` puts the foes on the flanks. The party starts on the side it came from.
- `feature=<thing>@<where>` and `hazard=<kind>@<where>` use the grammar of `site set` points of interest. `where` is `party`, `center` or `foes`.
- `boss=` creatures, and any NPC file, are DM-played by default (section 4).
- `encounter start ... --arena --change feature=...` adds features before the first move. After the first move, the layout is final.

### The source

The stage reads where the party is. It does not ask the DM.

| Source | Floor and walls | Props | The party returns to |
|---|---|---|---|
| A site room (crawl) | The theme tiles of the site | Points of interest and doors in the room become cover and objects | The same tile; the room is marked cleared |
| A saved scene | The LPC floor of the scene. A top-down DCSS wall for the template, because LPC walls face the front | Scene props become obstacles by zone (back-left prop: top left of the arena) | The same scene, with a new beat |
| Nothing (a road, an ambush) | A ground from the road or forest template. Trees and rocks at the edge | None. The DM adds features | The scene the DM names next |

A site room and a scene are both too small to walk in (a scene is 10 × 6 tiles with three rows of floor). So the arena is always a new room, saved as `{campaign}/stage/arenas/<encounter-id>.json`. A resumed game reloads it.

### Generator

Plain Python, seeded, no libraries. The same seed gives the same arena. The steps:

1. **Shell.** A room has walls and two door gaps. An open ground has sparse trees at the edge.
2. **Layout.** Open: three to five scattered obstacles. Chokepoint: a wall across the middle with a gap of three. Pillars: a grid of pillars with a clear lane. Chasm: a hazard band with a bridge of two tiles.
3. **Source props.** Scene props and points of interest go to their zone.
4. **DM features.** Each goes to the free tile nearest its `where`, outside the start columns.
5. **Starts.** The party stands in the first columns on the entry side. The foes stand opposite. An ambush puts two foes on the flanks.
6. **Check.** Every start tile must reach every other start tile. At least 90 percent of the floor must be reachable. If not, the generator tries the next sub-seed. After 60 tries it uses a plain open room.

Tile characters: wall, pillar, tree (block movement and sight); crate and table (block movement, give cover, do not block sight); hazard (lava or water; a unit that is pushed in takes 2d6); door; floor.

**Module layout.** The core grid code goes into a new module, `stage/arena.py`. It owns the tile grid, the tile atlas and renderer, line and sight, pathing and flood fill, and cover. `crawl.py` imports from it. `crawl.py` keeps what only a site needs: the floor generators, the seen-cell memory, walking, points of interest and wandering checks. Today these functions live in `crawl.py` (`visible`, `_sight`, `_line`, `path_to`, `_path`, `_flood`, `atlas_png`, `render_full`). Moving them is a refactor with no change in behavior. It is the first step of the work, before any board code, and `test_crawl` in `tests/test_stage.py` must pass unchanged. The arena generator is new code in `arena.py`.

### Light

`light=lit` is the default. A room is lit unless the DM or the theme says otherwise. In `dim` and `dark`, each unit has a vision radius:

- Darkvision: its range in tiles (60 ft is 12 tiles).
- A carried torch: 6 tiles.
- A lit prop (brazier, torch): 4 tiles.

The server computes the cells that the party sees (the crawl sight code, with these radii). It sends only those cells and the foes in them. Cells seen before stay dark on the map. Foes know where the party is unless the foe has no darkvision and the party is hidden.

## 2. The board

- **Grid.** One tile is 5 ft. Distance is the larger of the x and y difference. A diagonal move is allowed unless a blocking tile is at its corner.
- **Move.** A unit has its speed in tiles each turn. Dash adds the speed again. A click on a blue tile walks the shortest path.
- **Reach.** Melee needs distance 1. Ranged abilities have a range in tiles and need line of sight.
- **Sight.** A line between two tile centers (Bresenham, as in the crawl). Walls, pillars and trees stop it. Crates and tables do not.
- **Cover.** A ranged attack whose line crosses a crate or a table gets +2 AC for the target.
- **Reaction attacks.** A unit that leaves the reach of an enemy gives it one attack, unless the mover used Disengage. A reaction is the choice of its owner: the engine asks the player (section 5). A foe takes it by the engine or the DM, as for its turn.
- **Areas.** A zone ability has a center tile and a radius, a cone or a line. The board shows the covered tiles before the player confirms. An area hurts allies too.
- **Push.** A shove moves the target 5 ft away if the tile is free. A hazard tile deals 2d6.
- **Conditions and rounds.** The engine uses `encounter condition ... --rounds N` and `encounter use`. It does not keep its own copy.

## 3. Abilities: one format

```json
{"name": "Fireball", "cost": "action", "range_ft": 150, "shape": {"sphere_ft": 20},
 "save": ["dex", 15, "half"], "damage": [["8d6", "fire"]], "uses": {"per": "slot", "level": 3},
 "tags": ["area", "fire"]}
```

Fields: `cost` (`action`, `bonus`, `reaction`, `free`), `range_ft` or `reach_ft`, `shape`, `attack` (bonus) or `save` (ability, DC, success), `damage`, `conditions` (name and rounds), `uses` (`at-will`, `recharge` with dice and minimum, `per-day`, `per-rest`, `slot`), `tags`.

**Sources.**

- A PC card or list row comes from the character sheet and its class data.
- A monster action comes from the 5e API `actions`. Today `monster_record()` keeps only actions that have an attack roll or a save DC. It drops Multiattack, `reactions` and `legendary_actions`. The board must read them.
- A monster spell comes from the `Spellcasting` special ability. It is structured (level, DC, slots, spell list). The spell range, area and damage come from the spell data.
- An action with a `usage` field (for example `recharge on roll`, `1d6`, minimum 5) becomes a `uses` entry.

**Traits.** Many traits are plain text in `special_abilities`: Nimble Escape, Pack Tactics, Martial Advantage. The engine cannot read them. A small hand-written table (`stage/data/traits.json`) gives the common ones a rule. Every other trait that changes a turn is marked `dm_only`. A foe with a `dm_only` ability uses it only when the DM plays the turn.

## 4. Who plays the foes

There are three tiers.

| Tier | Foe | Who chooses |
|---|---|---|
| 1 | A plain monster with attacks only | The engine, by style |
| 2 | A monster with spells or area abilities | The engine, by score and style |
| 3 | A named foe, a boss, an NPC file, or a foe with a `dm_only` ability | The DM |

### Style

Each foe has a style. It sets the weights of the score. The DM sets it with `encounter start goblin:3 style=sneaky`. The default is `aggressive`.

| Style | Behavior |
|---|---|
| `aggressive` | Nearest target, most damage, ignores danger |
| `sneaky` | Weakest target first, uses cover, flanks |
| `cowardly` | Weights danger high. Flees at half HP |
| `skirmisher` | Ranged. Keeps distance. Kites |
| `support` | Heals and buffs allies first |

### The score

On its turn, the engine lists every legal play: a tile to move to (within speed), an ability, and a target or a center tile. It scores each play and takes the best one.

- Expected damage: hit chance times average damage, or failed-save chance times damage.
- A bonus for a kill.
- For an area: each enemy in it adds value and each ally in it subtracts value.
- A value for each condition that hurts the party.
- A penalty for the danger of the tile: how many enemies can reach it, and reaction attacks on the way.
- The style weights.
- A limited ability (a spell slot, a recharge, one use per day) must score above a threshold. For an area, the threshold is two or more enemies hit, or a kill.

A fireball is therefore not a script. The engine tests every tile it can see in range, keeps the one that hits the most PCs and no ally, and casts only if the score passes the threshold. A foe that cannot reach a good play uses a basic attack.

The board is 16 × 10 at most, so the engine can test every play.

### When the DM plays

The engine stops and sends the DM a prompt when:

- the foe is tier 3
- a PC has just done an improvised action
- a foe is bloodied for the first time and it is a boss
- the engine has no play with a score above zero

The prompt is short and lists only what the foe knows:

```
[combat] Grukk (bugbear, 27/27 HP) acts. Sireth 5 tiles, Astarion 6 tiles. Speed 6.
Morningstar +4, 2d8+2. Answer with one line.
```

The DM answers with the same commands as today (`attack`, `save`) and one movement line. A DM that does not answer in time lets the engine play the turn.

### Narration

The engine plays a whole round. Then it sends the DM one summary and the DM tells one beat. This is one DM call for each round, not one for each foe. The player or host can switch the summary off (see Settings). Then the DM hears only the prompts for DM-played foes.

```
[round 2] Goblin hit Sireth (6). Pyromancer burst missed Astarion. Sireth hit Goblin (dead). Grukk is next.
```

## 5. Players, phones and the table

The stage already has seats, one phone for each character, and the rule that only the player on turn may act (`server.py`, `api_input`). The board follows it.

- **Table screen.** Shows the board, the initiative bar, the log and the foe intents.
- **Phone.** Shows the hand of the character: cards or a list, the pips (action, bonus, reaction), the speed left and End turn.
- **Targeting on a phone.** A drag from a phone to a table screen is not possible. A tap on a card shows a list of valid targets with distance and hit chance. A tap on a target confirms. A tap on a tile confirms a tile ability. The table screen can also use drag.
- **Reactions.** When a reaction is possible, the engine pauses the foe turn and asks the phone of the owner. The question has two buttons and a time limit (see Settings). The limit starts when the question shows on the phone. If the seat is away, the engine skips the reaction.
- **Away seats.** The rule of `@away` stays: the engine skips the turn.
- **Skin.** The player picks cards or list on the phone. It is a setting of the seat.

## 6. Improvised actions and items

No prop is only decoration. A player can always try something the abilities do not list.

### Prop catalog (offline)

`stage/data/scenery.json` already lists the scene props. Each prop gets a `board` entry. It is written once, by hand:

```json
"barrel": {"board": {"blocks_move": true, "blocks_sight": false, "cover": "half", "hp": 10, "tags": ["flammable", "breakable", "heavy"]}}
```

Tags: `portable`, `fragile`, `flammable`, `heavy`, `climbable`, `breakable`, `light-source`. The tags give the default ruling. A prop with no tag still works with the free-text path.

Small objects (a bottle, a stone, a stool) can lie on a tile as items. A scene prop of the right kind becomes an item in the arena.

**First entries.** The first version covers the 15 board props of the five likely templates (tavern, cellar, dungeon, forest, street). `scenery.json` has 284 props. Wall features such as doors and windows are not on the board. The values below are the proposal. "Cover" is the cover a ranged attack gets when its line crosses the tile. "Sight" says if the prop blocks the line of sight. Only tall props block it.

| Prop | Blocks move | Blocks sight | Cover | HP | Tags |
|---|---|---|---|---|---|
| `barrel` | yes | no | half | 10 | flammable, breakable, heavy |
| `barrel_pile` | yes | no | half | 25 | flammable, breakable, heavy |
| `bush` | no | no | none | | flammable, concealing |
| `chair` | no | no | none | 5 | portable, breakable, flammable |
| `chests` | yes | no | half | 15 | heavy, container |
| `column_broken` | yes | no | three-quarters | | climbable, heavy |
| `dresser` | yes | no | half | 15 | heavy, flammable, breakable, container |
| `hearth` | yes | no | half | | heavy, light-source, hot |
| `mushroom` | no | no | none | | portable, fragile |
| `oak` | yes | yes | | | climbable, flammable |
| `pine` | yes | yes | | | climbable, flammable |
| `stones` | no | no | none | | portable |
| `stool` | no | no | none | 3 | portable, breakable, flammable |
| `stump` | yes | no | half | | climbable, heavy |
| `tree` | yes | yes | | | climbable, flammable |

A blank HP means the prop cannot be broken in a fight. `concealing` lets a unit behind it try Hide.

**A prop without an entry.** It blocks movement, gives no cover and has no tags. It is still a valid object. The DM can use it in a fight, and must then give it its stats on the fly, with the Improvise ruling (block move, block sight, cover, HP, tags). A prop that comes up often is a candidate for a new catalog entry. This note must go into the DM skill (`game/.claude/skills/combat/SKILL.md`) in the same change that adds the board commands. It is not there yet, because the commands do not exist yet.

### The flow

1. The player picks **Improvise** in the hand, or clicks an object. The player types what the character tries.
2. The engine suggests a ruling from the tags and the 5e rules. The default for a thrown object is the improvised weapon rule: 1d4 damage, range 20/60 ft, no proficiency. Picking up an object is the one free object interaction of the turn.
3. The engine sends the DM the text and the suggestion.
4. The DM confirms or changes the ruling.
5. The engine runs it with the normal roll window.

### Ruling

A ruling has a fixed shape:

| Field | Values |
|---|---|
| `cost` | `action`, `bonus`, `free` |
| `roll` | An attack (ability, to-hit bonus, target AC) or a check (skill, DC) |
| `effect` | Damage, a condition with rounds, a push, a terrain change, an object moved |
| `consume` | The object, yes or no |

The engine applies a ruling with the commands that exist: `attack <who> spell <target> --damage 1d4 --type bludgeoning --cost action`, `encounter condition <target> add blinded --rounds 1`, and `encounter use`. It does not add a second rules path.

**Example.** "I throw the wine bottle in the goblin's face." Default: a free interaction to pick it up, the action to throw, Dex attack against AC. The DM adds: on a hit, the goblin is blinded until the end of its next turn.

### Items

The character sheet keeps the whole inventory. The hand shows only what a player can use now.

| Kind | Example | In combat |
|---|---|---|
| Weapon | rapier, shortbow | An equipped weapon gives an attack ability. The first weapon change in a turn is a free object interaction. A second change costs the action. Ammunition counts down. At 0 the ability turns off. |
| Armor and shield | studded leather | Passive. It sets AC. A change is not possible in a fight. The engine says so and shows how long it takes. |
| Consumable | potion of healing, alchemist's fire, holy water | An ability with a quantity. Using it costs what its profile says (the action by default), removes one, and runs the effect. |
| Magic or perk item | a +1 sword, a wand | A perk compiles to an effect. A wand or a similar item grants an ability with its own uses. |
| Light source | torch, lantern | Sets the vision radius of the holder in `dim` and `dark` rooms. |
| Tool and gear | rope, thieves' tools, crowbar | No card. The player uses it with Improvise. |
| Item on the board | a bottle, a dropped potion | Pick up (free object interaction) or throw. A fallen foe leaves its items on its tile. |

**The hand.** On the phone, the hand is: the class abilities and the equipped weapons, then up to three pinned items, then **Items**, then **Improvise**. **Items** opens a drawer with every usable inventory row: name, quantity, cost and a Use button. A row that does not fit the turn (no action left) is dim. A player pins an item with the pin button. The default pins are healing potions and thrown items. The table screen shows no inventory. It shows only the result (the log), items on tiles, and light.

**Targets.** A potion goes on the user or on an adjacent ally. Giving a potion to an ally is an action. A thrown item follows the ability rules: range, cover and area. Handing an item to an adjacent ally is a free object interaction.

**Profiles.** Inventory entries today have a name, a quantity, a weight, a description, a rarity and an equipped flag. They have no effect data. An optional `profile` field gives an item its ability (cost, range, effect, uses). Old saves stay valid because the field is optional. The sources of a profile are:

1. The 5e equipment and magic item data, where it has structure.
2. A small hand-written table for the common consumables: healing potions, alchemist's fire, acid, oil, holy water, antitoxin, caltrops, ball bearings.
3. A DM ruling. The DM can save an approved improvised ruling as the profile of an item. The next use runs without the DM.

**Engine calls.** `character item <name> remove` for use, `character equip` for a weapon change, `encounter heal` and `encounter damage` and `encounter condition` for the effect. The board adds no second inventory.

**The Sheet button.** In a fight it is read-only, plus the actions above. Equipping armor, dropping items and trading between sheets wait for the end of the fight.

## 7. After the fight

### XP

The engine does this. `combat.end` splits the XP of defeated foes among the party. Two gaps must close:

- `npc_record` sets `xp` to 0, so a named NPC gives no XP. The NPC file gets an `xp` field, and the engine reads it.
- A foe that flees, yields or is talked down gives nothing. `encounter end --resolved <id>` marks a foe as beaten without a kill. It then counts.

### Loot

The engine rolls. The DM decides.

- **Catalogs.** Equipment and magic items, with rarity, from the 5e data in `.cache`. A small perk catalog: a name, the item types it fits, a rarity weight, and an effect.
- **Rarity sets power.** Common: no perk. Uncommon: one small perk. Rare: two. Very rare: strong perks. Legendary: a unique item that the DM writes.
- **Roll.** `uv run dnd-cli loot roll --cr 1 --kind individual|hoard --seed N` picks coins and items from the CR and the foe types. The same seed gives the same list. The stage shows the list to the DM, not to the players.
- **Control.** The DM can accept, reroll, swap an item, or force one: `loot force longsword perk=keen`. A perk can be free text. The DM writes the lore.
- **Effects.** A perk compiles to an effect (see `dnd-cli effect add`). A +1 weapon changes the roll without new code.

I did not check whether the 5e data has the DMG treasure tables. If it does not, a small table by CR is enough for a first version.

### Return

- From a site room: the party stands on the tile where it stood, the room is marked cleared, and `@explore <site-id>` shows the site again.
- From a scene: the DM shows the next beat with `@scene`.
- The arena file stays on disk until the campaign is saved over.

## 8. Settings

Two settings change how a fight feels. A host can change both during play.

| Setting | Values | Default | Meaning |
|---|---|---|---|
| `reaction_seconds` | 0 to 60 | 10 | Time to answer a reaction question. The time starts when the question shows on the phone. 0 means no limit. |
| `round_summary` | `on`, `off` | `on` | One summary and one narration beat for each round. |

- A default is saved in `game/settings.json` (per machine, as the agent setting is today). A running game keeps its own value in the stage state. A change during play changes the running game and does not change the saved default, unless the host ticks "make this the default".
- `encounter start ... summary=off` or `reaction_seconds=20` overrides one setting for one fight.
- The existing `POST /api/settings` works only from the menu (`menu_gate`). The board needs a new host-only route for play time: `POST /api/combat/settings`.
- The server starts the reaction timer when it sends `react_ask` to the phone. It uses the server clock. A slow phone does not gain time.

## 9. Server API (draft)

| Route | Use |
|---|---|
| `GET /api/arena` | The seen part of the arena, the units in sight, the turn, the intents. |
| `POST /api/arena/move` | `{to: [x, y]}`: walks, spends speed, returns the new view and the reasons it stopped. |
| `POST /api/arena/act` | `{ability, target}` or `{ability, at: [x, y]}`: runs the ability through `combat.py`. |
| `POST /api/arena/react` | `{id, take: true\|false}`: answers a reaction question. |
| `POST /api/arena/improvise` | `{text, object?}`: sends the text and the engine suggestion to the DM. |
| `POST /api/combat/settings` | Host only. `{reaction_seconds?, round_summary?, make_default?}`. |
| `POST /api/end-turn` | Exists today. Ends the turn. |

Stage events: `arena {id}`, `turn {who}`, `react_ask {who, by, ability}`, `round_summary`. The state gets `arena` (the id, or null).

## 10. Not in this version

- No fight inside the scene view, and no front and back ranks. The arena covers every fight, even a talk that turns bad.
- No multi-level arenas, no flying, no 3D height.
- No grapple, swallow or other rules that move a unit by force, except the push. These are `dm_only`.
- No lair actions or legendary actions on the engine side. The DM plays them.
- No terrain that changes by itself (spreading fire).
- No attunement limit and no encumbrance in a fight.

## 11. Decisions

Settled:

- **Module layout.** The core grid code goes into `stage/arena.py`. `crawl.py` extends it (section 1).
- **Reaction time.** A setting, 10 seconds by default, changeable during play (section 8).
- **Round summary.** A setting. The default is on. The player or host can change it, and one fight can override it (section 8).
- **Perk catalog.** It waits. It is tracked as GitHub issue #1, not in this file.
- **First prop entries.** The 15 props of the tavern, cellar, dungeon, forest and street templates (section 6). Other props work with stats given on the fly. The DM note goes into the combat skill when the board ships.

Open:

- **Item profiles.** Is the hand-written table of common consumables enough for the first version? Which items does the first campaign need?
- **Attunement and encumbrance.** Not enforced in this version. Do you want either one?
