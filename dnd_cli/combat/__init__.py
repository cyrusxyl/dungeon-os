"""Rules engine for the DM: encounters, attacks, saves, checks, damage, XP.

The DM decides what happens; this module does the bookkeeping and the
arithmetic, and prints one short line per result. A combatant is one record
whatever its source:

- a player character (`characters/<id>.json`, saved through dnd_cli.character),
- a monster instance (`goblin#2`), built from the D&D 5e API at encounter start
  and kept in `state.json` -> `active_encounter.monsters`,
- an NPC with stats (`world/npcs/<id>.json` with `hp` and `armor_class`),
  copied into the encounter and written back at the end.

Ids are the visual stage's actor ids, so `goblin#2` works in `@enter` and in
`attack`. Rolls go to the stage's dice box unless `secret`; the stage event
never carries a hidden number (monster HP, AC, a secret DC).

The rules are in the modules of this package. Import the module you need:
`tracker` (state, teams, conditions), `records`, `rolls`, `wounds`, `smite`, `encounters`, `resolve`.
Each module imports only modules to its left in that list, and `encounters` does not import `smite`.
"""
