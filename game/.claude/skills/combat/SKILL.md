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

## Each turn

```bash
uv run dnd-cli attack aragorn longsword goblin#2            # to hit vs AC, damage on a hit, applied
uv run dnd-cli attack goblin#1 scimitar sireth --adv         # --adv / --dis from conditions and position
uv run dnd-cli attack legolas spell goblin#3 --damage 1d10 --type fire    # spell attack (Fire Bolt)
uv run dnd-cli save goblin#1 goblin#2 dex --dc 15 --damage 8d6 --type fire --half    # Fireball
uv run dnd-cli save sireth --from dragon:fire-breath         # a creature's DC action: DC, damage, half from the API
uv run dnd-cli encounter next                                # next living combatant; conditions count down
```

- `attack <attacker> <weapon or action> <target>`. The weapon name can be part of the name (`long` for Longsword). A natural 20 is a critical hit (dice doubled), a natural 1 misses. `--bonus 2` for Bless or `--bonus -2` for half cover.
- A PC's spells: cast first with `uv run dnd-cli character cast <name> <level>` (it refuses when no slot is left), then `attack ... spell ...` or `save ...`.
- Multiattack is narration: make each attack with its own `attack` command.
- Damage or healing outside an attack: `uv run dnd-cli encounter damage goblin#2 7 --type fire`, `uv run dnd-cli encounter heal sireth 8`. A hit on a creature that is `concentrating` prints the concentration DC.
- Conditions: `uv run dnd-cli encounter condition goblin#1 add poisoned --rounds 3 --save con:11`, `... remove poisoned`. `encounter next` counts rounds down on the creature's turn, ends expired conditions, and says which saves are due. Mark concentration with the condition `concentrating`.
- `uv run dnd-cli encounter status` prints the order, HP, AC and conditions — use it instead of reading files.
- A PC at 0 HP: on its turn, `uv run dnd-cli check <name> death`. Damage to a PC at 0 adds death-save failures by itself; any healing resets them.

## End

```bash
uv run dnd-cli encounter end            # XP of defeated foes, split among the party; clears the tracker
uv run dnd-cli encounter end --no-xp    # the party fled, or the foes surrendered without a fight
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
