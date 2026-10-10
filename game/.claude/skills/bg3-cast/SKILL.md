---
name: BG3 Cast
description: Baldur's Gate 3 companions and major NPCs for the DM — Astarion, Shadowheart, Gale, Wyll, Lae'zel, Karlach, Halsin, Jaheira, Minsc, Minthara, Cazador, Orin, Gortash, Ketheric Thorm. Gives voice, wants, secrets and an era state for each, and the sheet and look hand-offs. Load when a BG3 character appears, talks, joins the party, or must be built as a sheet.
---

# BG3 Cast

Use with `bg3-setting` for lore. Same precedence: `canon.json` > `dm_story.md` > this skill.

## Rules for using a BG3 character
1. Pick the era first. A `[1492]` secret is not true in a `[1480s]` scene. The cast table gives an era state per person.
2. The campaign may rewrite a person (the active campaign gives Astarion the background "Disgraced Magistrate"). Read the character file before you play them.
3. Play the voice and the want. Reveal a secret in three clues, not one speech (`dm-craft-principles`).
4. An NPC does not obey the party because of fame. Use `social`. A refusal is a valid result.
5. Dice results are final (anti-drift rules). A companion's personal quest changes only through play.

## Building a sheet
Follow `character-creation` (flags at "pitch names existing characters"). Do not hand-write JSON. Then set the look with `stage`.

Races and backgrounds now work for all ten companions:
- Githyanki: `--race githyanki`. Drow: `--race elf --subrace drow`. Wood elf: `--race elf --subrace wood-elf`. High half-elf: `--race half-elf`, and name the high-elf blood in the backstory.
- Backgrounds: charlatan, folk-hero, outlander, noble, acolyte; and sage, soldier, criminal with `--background-bonus` (see `character-creation`).
- Zariel tiefling (Karlach): `--race tiefling`. The Zariel line is not in the data yet (gap L1/R4 in the gap doc).
- Subclasses (Trickery, Battle Master, Moon, Vengeance, Arcane Trickster) are reference data only: `uv run dnd-cli get subclasses/<index>`. The engine does not apply them.
Do not hand-edit a sheet to get around a missing option.

## Read next
`references/companions.md` for the table and voices.
