---
name: Combat Resolution
description: Handle D&D 5e combat encounters including initiative, attacks, damage, HP tracking, conditions, status effects, and turn coordination. Use when combat starts, players attack, enemies engage, spells apply conditions, or initiative is rolled. Supports multi-player coordination and condition enforcement.
---

# Combat Resolution

The `dnd-cli` rules commands do all combat bookkeeping: initiative, to-hit against AC, damage dice and crits, resistances, HP for player characters and creatures, conditions and their durations, turns, death saves, XP. **You decide what happens and narrate it.** Do not roll, add, or edit HP by hand. Each command prints one short line per result, and shows the dice on the stage (add `--secret` for a roll behind the screen).

Ids are the stage's actor ids: `goblin#1` in `attack` is `goblin#1` in `@enter`.

## Start

```bash
uv run dnd-cli encounter start goblin:3 boss=bugbear
uv run dnd-cli encounter start bandit:2 cassara-whitmore --pcs sireth
```

- `goblin:3` makes `goblin#1`..`goblin#3` from the 5e API (HP, AC, actions, saves, XP). `boss=bugbear` gives one creature its own id. An id with a `world/npcs/<id>.json` file that has `hp` and `armor_class` joins as that NPC; its HP is written back at the end.
- The party joins by default (`--pcs a,b` to choose). The command rolls initiative for everyone and prints the order and each creature's AC, HP and resistances.
- No API monster fits? `uv run dnd-cli search monsters --name <word>` for the index.
- Reinforcements: `uv run dnd-cli encounter add wolf:2`.

## A fight on a board

Add `--arena` (last) to get a board: the players walk their characters, and the stage plays the creatures. Use it for any fight where position matters: a room, a field, an ambush.

```bash
uv run dnd-cli encounter start goblin:2 boss=bugbear --arena layout=pillars size=medium light=lit
uv run dnd-cli encounter start wolf:3 --arena ambush=yes feature=barrels@party hazard=water@center
```

- `layout=` is `open`, `chokepoint`, `pillars` or `chasm`; `size=` is `small` (12 x 8) or `medium` (16 x 10); `light=` is `lit`, `dim` or `dark`; `ambush=yes` puts creatures on the flanks; `theme=` takes the tiles of a site theme; `seed=` repeats a layout.
- `feature=<thing>@<where>` adds an object: `cover`, `pillar`, `barrels`, or any prop of the scene catalog. `hazard=lava@center` or `hazard=water@foes` adds a pool. `where` is `party`, `center` or `foes`. **Never give coordinates**: the stage places everything, and a layout never changes after the start.
- The arena is built from where the party is: the room of the site they explore, the scene on the stage, or an empty field. You do not need `@scene` for it. `@scene` or `@explore` after the fight shows the story again.
- The command prints who you play: a creature with its own id (`boss=bugbear`) or an NPC file. **The stage plays every other creature.** Do not run their turns, and do not call `encounter next` for them.
- When a creature you play is up, you get `[combat] Round 1: Grukk (boss) acts, and you play it. ...`. Then: `uv run dnd-cli encounter move boss --toward aragorn` (or `--to 7,4`), `uv run dnd-cli attack boss morningstar aragorn`, narrate one beat, `uv run dnd-cli encounter next`. The board checks speed, blocked cells, reach, sight and cover, and prints why it refuses. A player gets a reaction question when a creature leaves their reach: the walk waits for the answer.
- `uv run dnd-cli arena show` lists the props, items and who stands where. `uv run dnd-cli arena preview` makes a picture for you (not for the players). Describe positions in words (the pillar on the left, the pool in the middle).
- Card actions and End turn do not reach you on a board. You hear when a creature you play is up, and when no creature is left standing (`[combat] Every creature is down ...`): narrate the end, then `uv run dnd-cli encounter end`.
- **Props.** Only 15 props have board stats (barrel, barrel_pile, bush, chair, chests, column_broken, dresser, hearth, mushroom, oak, pine, stones, stool, stump, tree). Any other prop still works in a fight: it blocks movement and gives no cover. Give it stats on the fly when the story needs them (cover behind a table, a chandelier that falls) and rule it from the 5e rules with the commands you have (`attack ... --damage`, `encounter condition`, `encounter use`). A player may try anything with the props, the items and the room: decide, say what it costs (action, bonus action or free object interaction), roll with the commands, and narrate.
- **Improvise.** A player picks Improvise in the hand and types what the character tries. You get `[combat] Aragorn (aragorn) improvises: "...". Object: ... Suggested ruling: ...`. The suggestion is a default from the words and the tags of the object. Confirm it or change it (a different DC, a condition, no cost), run it with `attack <id> improvised <target> --damage 1d4 --type bludgeoning --bonus <to-hit>` (`improvised` has no attack bonus of its own: `--bonus` is the whole to-hit; add `--cost` if it is not an action), `encounter condition`, or `encounter use <id> action` when no attack spends the action, and narrate one beat. Do not call `encounter next`: it is still that player's turn. Say no only when the rules say it cannot be done, and then say what the character can do instead. The board cannot remove a prop or move an object: narrate it. When a ruling on an item is good for next time, save it as the profile of the row: `uv run dnd-cli character item aragorn profile "Smoke bomb" --profile '{"kind": "throw", "range_ft": 20, "damage": ["1d6", "fire"]}'` (or `{"kind": "heal", "heal": "2d4", "cost": "bonus"}`). The item then has a card, and the next use runs without you.
- `encounter add wolf:2` puts reinforcements on a free cell near the creatures' side.

## Each turn

```bash
uv run dnd-cli attack aragorn longsword goblin#2            # to hit vs AC, damage on a hit, applied
uv run dnd-cli attack goblin#1 scimitar sireth --adv         # --adv / --dis from conditions and position
uv run dnd-cli effect add sireth bless                        # bonus dice and advantage a character carries: the next rolls use them
uv run dnd-cli attack legolas spell goblin#3 --damage 1d10 --type fire    # spell attack (Fire Bolt)
uv run dnd-cli save goblin#1 goblin#2 dex --dc 15 --damage 8d6 --type fire --half    # Fireball
uv run dnd-cli save sireth --from dragon:fire-breath         # a creature's DC action: DC, damage, half from the API
uv run dnd-cli encounter next                                # next living combatant; conditions count down
```

- `attack <attacker> <weapon or action> <target>`. The weapon name can be part of the name (`long` for Longsword). A natural 20 is a critical hit (dice doubled), a natural 1 misses. `--bonus 2` for Bless or `--bonus -2` for half cover.
- A PC's spells: cast first with `uv run dnd-cli character cast <name> <level>` (it refuses when no slot is left), then `attack ... spell ...` or `save ...`.
- Multiattack is narration: make each attack with its own `attack` command.
- A weapon or spell hit always goes through `attack` (or `save`), so the players see the roll. Never use `encounter damage` for a hit, and never use `--secret` on an attack or a save against a player character: the player must see what hit them. Use it only for what has no roll: a trap, a fall, a hazard. It shows a line in the log.
- Damage or healing outside an attack: `uv run dnd-cli encounter damage goblin#2 7 --type fire`, `uv run dnd-cli encounter heal sireth 8`. A hit on a creature that is `concentrating` prints the concentration DC.
- Conditions: `uv run dnd-cli encounter condition goblin#1 add poisoned --rounds 3 --save con:11`, `... remove poisoned`. `encounter next` counts rounds down on the creature's turn, ends expired conditions, and says which saves are due. Mark concentration with the condition `concentrating`.
- `uv run dnd-cli encounter status` prints the order, HP, AC and conditions — use it instead of reading files.
- A PC at 0 HP: on its turn, `uv run dnd-cli check <name> death`. Damage to a PC at 0 adds death-save failures by itself; any healing resets them.

## The player's turn on the stage

The stage gives a player character a turn like Baldur's Gate 3: the turn bar shows the order, and the character card has the action, bonus action and reaction icons, the common actions (Attack, Shove, Dash, Disengage, Dodge, Help, Hide), class features and an End turn button. The game spends the icons. You do not toggle them.

- On a player character's turn, **wait**. The player acts from the card, or types a line. Do not play their turn in prose and do not call `encounter next` for them.
- A card action reaches you as a line like `[Aragorn acts from the character card] aragorn Longsword → goblin#1: ... hit, 7 damage. Narrate it. It is still their turn.` Narrate it in a beat and stop. The attack is already rolled and applied.
- Hide and Shove are rolled in the roll window. The result reaches you as `[Aragorn rolled in the roll window] ...` with a note. Decide with the rules: Hide against the enemies' passive Perception (`uv run dnd-cli check <enemy> perception --passive`); if it works, `uv run dnd-cli encounter condition <pc> add hidden`. Shove against the target's Athletics or Acrobatics (`uv run dnd-cli check <enemy> athletics --dc <the player's total>`, or the better of the two). A hidden attacker rolls with advantage on its next attack; `attack` does that and removes `hidden`.
- Dash, Disengage, Dodge and Help are conditions that last one round (`dashing`, `disengaged`, `dodging`, `helping`). `attack` gives disadvantage against a `dodging` creature by itself. A creature that moves away without `disengaged` gives an opportunity attack: use `attack ... --cost reaction`.
- When the player ends the turn you get `[Aragorn ends their turn] Round 1: goblin#1's turn ... ` and the tracker is already on the next creature. Run each creature's turn with `attack` or `save`, narrate it, then `uv run dnd-cli encounter next`. Stop when a player character is up and ask nothing: the stage shows "Your turn".
- Free-text turns still work. `attack` spends the action by itself (`--cost bonus`, `--cost reaction`, or `--cost free` for an extra attack of the same action). For anything else, `uv run dnd-cli encounter use <id> action|bonus|reaction` marks it used (`--free` gives it back).
- **Every hit and miss gets a wound description.** The player sees no HP, so the text is how they judge the fight. After each attack (yours for a creature, or the player's from the card) narrate what the blow did and how the target looks now. Scale it to the damage against the creature's max HP: a graze or a shrug (under a quarter), a solid wound (about a third), a crippling hit (half or more), then limping, bloodied, staggering, barely standing, down. Show what changed since the last blow. A miss says how it missed (parried, dodged, glanced off armour). Never give HP, AC or damage numbers; keep the words in line with the band the stage shows (unhurt, injured, bloodied at half, near death at a quarter).
- Players see a creature's name, its place in the order, its conditions and how hurt it looks (unhurt, injured, bloodied, near death, down). They never see its HP or AC. Describe wounds in the story to match.
- Bonuses (Guidance, Bless, Bardic Inspiration) are on the card only when a party member can give them: a known spell or a Bardic Inspiration use. You may still grant one the story earns with `uv run dnd-cli effect add <who> <effect>`.

## End

```bash
uv run dnd-cli encounter end            # XP of defeated foes, split among the party; clears the tracker
uv run dnd-cli encounter end --no-xp    # the party fled, or the foes surrendered without a fight
uv run dnd-cli encounter end --resolved goblin#2 mira   # a foe that fled, yielded or was talked down still gives its XP (a named NPC gives the `xp` of its file)
uv run dnd-cli loot roll --cr 1 --kind hoard --seed 7        # coins and items by CR (individual or hoard); the same seed gives the same list, another seed rerolls
uv run dnd-cli loot roll --cr 2 --type beast                 # a beast, an ooze or a plant carries nothing
uv run dnd-cli loot force "Longsword" --to aragorn --perk "keen: it hums near orcs" --rarity uncommon   # give an item you chose, with a perk in your own words
```

It prints "LEVEL UP READY" for a character who reached the next level (see the `character-advancement` skill). Then offer a search, loot, or a rest (`uv run dnd-cli rest short` / `rest long`).

## Conditions: what to apply

Give `--adv` or `--dis` from these when you call `attack`, `save` or `check`:

| Condition | Its own rolls | Rolls against it |
|---|---|---|
| Blinded | attacks: disadvantage; sight checks fail | attacks: advantage |
| Frightened | checks and attacks: disadvantage while the source is in sight; cannot move closer | — |
| Invisible | attacks: advantage | attacks: disadvantage |
| Poisoned | attacks and checks: disadvantage | — |
| Prone | attacks: disadvantage | melee within 5 ft: advantage; ranged: disadvantage |
| Restrained | attacks and DEX saves: disadvantage; speed 0 | attacks: advantage |
| Grappled | speed 0 | — |
| Paralyzed, Stunned, Unconscious | no actions; STR and DEX saves fail | attacks: advantage; melee within 5 ft crits (paralyzed, unconscious) |
| Charmed | cannot harm the charmer | charmer: advantage on social checks |
| Exhaustion 1-6 | 1 checks dis; 2 speed half; 3 attacks and saves dis; 4 HP max half; 5 speed 0; 6 death | — |

Full text: `uv run dnd-cli info conditions <name>`.

## Multi-player

- Before a player acts, the character must be theirs (`players/{id}.json`, also in the session brief).
- Name whose turn it is and which player controls the character.
- Reactions and readied actions: resolve in initiative order, with your judgment.

## Tips

- Narrate first, mechanics second: "Your arrow flies true (18 vs AC 15) — 7 damage."
- Keep combat moving: prompt the player whose turn it is.
- Never invent AC or HP: `encounter status` has them.
