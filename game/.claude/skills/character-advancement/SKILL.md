---
name: Character Advancement
description: Handle D&D 5e character leveling, ability score improvements, feat selection, and feature acquisition. Use when characters gain XP, reach new levels, or need to update their progression. Validates level-appropriate benefits and tracks multiclassing.
---

# Character Advancement

Guide players through leveling up with API-validated features, spell progression, and ASI/feat selection.

## XP

- After a fight, `uv run dnd-cli encounter end` splits the XP of the defeated foes.
- Milestones, quests, clever play: `uv run dnd-cli character xp all --amount 300` (or named characters).
- Both print **LEVEL UP READY** when a character reaches the next level. The command knows the XP table.

## Level-Up

```bash
uv run dnd-cli character level-up sireth                     # average HP (die / 2 + 1 + CON)
uv run dnd-cli character level-up sireth --hp roll           # the player rolls for HP
uv run dnd-cli character level-up sireth --asi dex+2         # a level with an Ability Score Improvement
uv run dnd-cli character level-up sireth --asi none          # ...when the player takes a feat instead
```

One command does the whole level from the 5e API: level, HP and hit dice, proficiency bonus, every skill, save and weapon bonus, spell DC and attack bonus, spell slots, and the new class features (written into `features_and_traits` with a short description). It keeps each skill's proficiency or expertise as it was. It prints the gains, the class resources (rage, ki, sneak attack…), and how many spells the character may know.

You and the player still choose:
1. **ASI or feat** (levels 4, 8, 12, 16, 19 for most classes; the command refuses until you give `--asi`). +2 to one score or +1 to two; no score above 20. A feat: `uv run dnd-cli get feats/<index> --fields name,desc,prerequisites`, check the prerequisites, then add it to `features_and_traits` with the Edit tool (text only; a +1 score from a half-feat goes in `--asi str+1`).
2. **New spells** (known casters, wizards' two spells per level): `uv run dnd-cli search spells --class <class> --level <n>`, then add the choices to `spellcasting.spells_known` with the Edit tool.
3. **Subclass features** are not in the API's base class data: add them by hand from the player's choice.

Then narrate the level in one short beat: "Sireth reaches level 4 — HP 31, Ki 4."

## Multiclassing

When a character takes a level in a different class:

### Step 1: Check Prerequisites

**Multiclass prerequisites**:
- Barbarian: STR 13
- Bard: CHA 13
- Cleric: WIS 13
- Druid: WIS 13
- Fighter: STR 13 or DEX 13
- Monk: DEX 13 and WIS 13
- Paladin: STR 13 and CHA 13
- Ranger: DEX 13 and WIS 13
- Rogue: DEX 13
- Sorcerer: CHA 13
- Warlock: CHA 13
- Wizard: INT 13

**Verify**: Read character's ability scores, ensure they meet both current class and new class prerequisites.

### Step 2: Proficiency Restrictions

When multiclassing, you don't get all starting proficiencies:

**Multiclass proficiency gains** (check class tables):
- Barbarian: Shields, simple weapons, martial weapons
- Bard: Light armor, one skill, one musical instrument
- Cleric: Light armor, medium armor, shields
- Druid: Light armor, medium armor, shields
- Fighter: Light armor, medium armor, shields, simple weapons, martial weapons
- Monk: Simple weapons, shortswords
- Paladin: Light armor, medium armor, shields, simple weapons, martial weapons
- Ranger: Light armor, medium armor, shields, simple weapons, martial weapons, one skill
- Rogue: Light armor, one skill, thieves' tools
- Sorcerer: None
- Warlock: Light armor, simple weapons
- Wizard: None

Add only these proficiencies, not all starting proficiencies.

### Step 3: Calculate Multiclass Spellcasting

If multiclassing with multiple spellcasting classes:

**Full casters** (Bard, Cleric, Druid, Sorcerer, Wizard): Class level = caster level
**Half casters** (Paladin, Ranger): Class level ÷ 2 = caster level
**Third casters** (Eldritch Knight, Arcane Trickster): Class level ÷ 3 = caster level

**Total spell slots**: Sum caster levels, use combined level for spell slot progression.

**Spells known**: Track separately per class (Bard 3 knows Bard spells, Wizard 2 knows Wizard spells).

### Step 4: Track Class Levels

Update character file with multiclass structure:

```json
{
  "class": "Fighter 5 / Wizard 2",
  "classes": [
    {
      "name": "Fighter",
      "level": 5,
      "hit_die": "d10"
    },
    {
      "name": "Wizard",
      "level": 2,
      "hit_die": "d6"
    }
  ],
  "level": 7
}
```

### Step 5: Apply Level-Up from New Class

Follow level-up workflow but use the new class's features, hit die, and spell list.

## Downtime Training

If using downtime rules for level-up:

**Training time**: (New level - current level) × 10 days
**Cost**: (New level - current level) × 25 gp per day

Track training progress in character notes.

## API Endpoints Reference

**Class Levels**:
- List levels: `GET /api/2014/classes/{index}/levels`
- Specific level: `GET /api/2014/classes/{index}/levels/{level}`
- Level features: `GET /api/2014/classes/{index}/levels/{level}/features`

**Features**:
- List: `GET /api/2014/features`
- Details: `GET /api/2014/features/{index}`

**Feats**:
- List: `GET /api/2014/feats`
- Details: `GET /api/2014/feats/{index}`

**Spells**:
- Class list: `GET /api/2014/classes/{index}/spells`
- Details: `GET /api/2014/spells/{index}`

## Tips

- **Let players decide**: ASI vs Feat is a major choice, don't rush them
- **Explain features**: Read feature descriptions aloud so players understand their new abilities
- **Update incrementally**: Apply each change to character file as you go
- **Recalculate everything**: Many stats depend on level, proficiency bonus, or ability scores
- **Save old HP**: Don't forget to update both current and max HP
- **Spell selection matters**: Help players choose spells that fit their character concept

## Common Mistakes to Avoid

- **Don't forget CON modifier for HP**: It applies every level
- **Don't skip proficiency bonus updates**: It affects many stats
- **Don't give full starting proficiencies for multiclass**: Use restricted list
- **Don't forget to recalculate spell save DC**: It changes when proficiency bonus increases
- **Don't allow ability scores above 20**: Unless magical items permit it
- **Don't skip feat prerequisites**: Some feats require specific scores or proficiencies

## Integration with Other Skills

- **After combat** → Award XP, check if characters leveled
- **Character creation** → Sets up initial level 1 character
- **During rest** → Players may choose to level up during long rest
- **Magic skill** → Handles spell selection and spellcasting mechanics
