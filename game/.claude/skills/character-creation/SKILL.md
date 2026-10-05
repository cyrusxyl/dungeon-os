---
name: Character Creation
description: Create a level 1 D&D 5e character. Talk the choices through with the player, then run one command that builds the sheet, the player file, and the party entry. Use when a player wants a new character.
---

# Character Creation

## On the visual stage

Never run the question workflow below on the stage. The player makes characters on the creation screen (the **New character** button in the party panel). The server builds the sheet.

- A player asks for a new character: send one short beat that points to the **New character** button. Do nothing else.
- A prompt says characters were made on the creation screen: for each id, run `uv run dnd-cli character show <id>`. Read `hooks` and `backstory`. Do not change the sheet or the look. Use the hooks with the `worldbuilding` skill.
- The pitch names existing characters (for example a Baldur's Gate 3 epilogue): for each one, run `character new` at level 1 (flags below). Then run `uv run dnd-cli character level-up <id> --asi <asi>` once per level, up to the target level. Pass `--asi` on an ASI level (the command refuses without it and says so). Use `str+2` or `str+1,dex+1`, or `none` for a feat. `--hp avg` (default) or `--hp roll` sets the HP. Then set the look (`stage` skill).

## In the classic terminal view (`--classic`)

The workflow below is for this view only.

You talk through the choices. The program does the arithmetic. Do not write the sheet JSON by hand. Do not edit `state.json` or the player file for a new character.

## Lookups

Use `uv run dnd-cli get <endpoint> --fields ...`. Do not use curl or pipes. Ask for only the fields you need.

```bash
uv run dnd-cli get races                      # list
uv run dnd-cli get races/elf --fields name,speed,ability_bonuses,traits,subraces
uv run dnd-cli get subraces/high-elf --fields name,ability_bonuses,racial_traits
uv run dnd-cli get classes/wizard --fields name,hit_die,proficiency_choices,saving_throws
uv run dnd-cli get classes/wizard/levels/1 --fields spellcasting
uv run dnd-cli get backgrounds/acolyte --fields starting_proficiencies,feature
uv run dnd-cli search spells --name magic     # find a spell index
uv run dnd-cli get equipment/longsword --fields name,armor_class,damage,properties
```

## Workflow

Ask one question at a time. On the visual stage, use one beat per question, with `@choices` for lists (see the `stage` skill). Give short options. Do not recite long rules.

1. **Race** (and subrace, if the race has one).
2. **Class.**
3. **Background.** The API has few backgrounds. If the background is not in the API, ask which two skills it gives. You pass them with `--background-skills`.
4. **Ability scores.** Offer one method:
   - Standard array: 15, 14, 13, 12, 10, 8.
   - Point buy: 27 points, scores 8 to 15.
   - Roll: `uv run roll 4d6kh3 -v`, six times.

   The player assigns the six scores to the six abilities. Racial bonuses come later, from the program. Half-elf: ask which two abilities get +1.
5. **Skills.** The class gives a fixed number of picks from its list. The background skills are extra. A skill cannot come from two sources.
6. **Spells** (casters only). Ask for cantrips, and for level 1 spells if the class has them.
7. **Gear.** Suggest the class starting weapon, armor, and shield. Use API equipment indexes.
8. **Name, alignment, player id.** Choose a short file id from the name.

Then run ONE command:

```bash
uv run dnd-cli character new <id> --player <player-id> --name "Name" \
  --race elf --subrace high-elf --class wizard --background acolyte \
  --scores 8,14,13,15,10,12 --assign str,dex,con,int,wis,cha \
  --skills arcana,history --cantrips fire-bolt,light,mage-hand --spells magic-missile,shield \
  --equipment quarterstaff --alignment "Neutral Good"
```

Options:
- `--background-skills a,b`: skills of a background that is not in the API.
- `--bonus-abilities dex,con`: half-elf only.
- `--languages a,b`: extra languages (for example, human).
- `--player-name Dana`: the player's name, for a new player file.

The scores are given in the order of `--assign`. The command adds racial bonuses and computes HP, AC, skills, saves, spell numbers, weapons, and features. It saves the sheet, adds the character to `party_members`, and updates the player file. If a value is wrong, the command says how to fix the call. Fix it and run it again. Nothing is written when it fails.

## After the command

1. Ask the player for personality traits, ideals, bonds, and flaws. Add them to `characters/<id>.json` with the Edit tool. Use the keys `personality_traits`, `ideals`, `bonds`, `flaws`.
2. Announce: "**Name has joined the party!** Welcome, race class."
3. Ask two questions: "What people or places from your character's past do you want to see again?" and "What unfinished problem does your character have?" Use the answers with the `worldbuilding` skill for the campaign's Player-Specific Hooks.
4. On the visual stage, set the look with the `actor` command (see the `stage` skill).
5. In session 0, make all party members one after the other. Leveling up is in the `character-advancement` skill.
