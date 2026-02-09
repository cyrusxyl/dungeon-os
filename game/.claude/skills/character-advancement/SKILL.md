---
name: Character Advancement
description: Handle D&D 5e character leveling, ability score improvements, feat selection, and feature acquisition. Use when characters gain XP, reach new levels, or need to update their progression. Validates level-appropriate benefits and tracks multiclassing.
---

# Character Advancement

Guide players through leveling up with API-validated features, spell progression, and ASI/feat selection.

## Level-Up Workflow

When a character gains a level:

### Step 1: Check Experience Requirements

**Experience thresholds** (for reference):
- Level 2: 300 XP
- Level 3: 900 XP
- Level 4: 2,700 XP
- Level 5: 6,500 XP
- Level 6: 14,000 XP
- Level 7: 23,000 XP
- Level 8: 34,000 XP
- Level 9: 48,000 XP
- Level 10: 64,000 XP
- Level 11: 85,000 XP
- Level 12: 100,000 XP
- Level 13: 120,000 XP
- Level 14: 140,000 XP
- Level 15: 165,000 XP
- Level 16: 195,000 XP
- Level 17: 225,000 XP
- Level 18: 265,000 XP
- Level 19: 305,000 XP
- Level 20: 355,000 XP

1. **Read character file**: Check current `level` and `experience_points`
2. **Confirm level-up**: "You've reached level {new_level}! Time to level up."

### Step 2: Query Level Benefits

Get class features for the new level:

```bash
curl -sL "https://www.dnd5eapi.co/api/2014/classes/{class-index}/levels/{level}" | jq '{
  level: .level,
  ability_score_bonuses: .ability_score_bonuses,
  prof_bonus: .prof_bonus,
  features: .features,
  spellcasting: .spellcasting,
  class_specific: .class_specific
}'
```

This returns:
- **ability_score_bonuses**: Number of ASIs available (typically 1 at levels 4, 8, 12, 16, 19)
- **prof_bonus**: Proficiency bonus for this level
- **features**: New features gained this level
- **spellcasting**: Spell slots and spells known/prepared
- **class_specific**: Class-specific resources (rage uses, ki points, sorcery points, etc.)

### Step 3: Roll Hit Points

**Hit Die**: Read character's class hit die (d6, d8, d10, or d12)

**Option 1: Roll**:
```bash
source .venv/bin/activate && roll 1d{hit_die} -v
```

**Option 2: Take average** (rounded up):
- d6 = 4
- d8 = 5
- d10 = 6
- d12 = 7

**Calculate HP increase**:
- HP_increase = roll_result + CON_modifier
- Minimum 1 HP per level

**Update character**:
- `hp.max` += HP_increase
- `hp.current` += HP_increase (if at full health)
- `hit_dice.total` += 1
- `hit_dice.remaining` += 1

### Step 4: Ability Score Improvement or Feat

If `ability_score_bonuses > 0` (typically levels 4, 8, 12, 16, 19):

**Option 1: Ability Score Improvement (ASI)**:
- Player chooses which abilities to increase
- Can add +2 to one ability, or +1 to two different abilities
- Cannot exceed 20 (without magical effects)
- Update `ability_scores` and recalculate `ability_modifiers`

**Option 2: Choose a Feat**:

1. **List available feats**:
   ```bash
   curl -sL "https://www.dnd5eapi.co/api/2014/feats" | jq -r '.results[] | "- \(.name) (\(.index))"'
   ```

2. **Player selects feat**, query details:
   ```bash
   curl -sL "https://www.dnd5eapi.co/api/2014/feats/{feat-index}" | jq '{
     name: .name,
     desc: .desc,
     prerequisites: .prerequisites
   }'
   ```

3. **Check prerequisites**: Verify character meets requirements (ability scores, proficiencies, etc.)

4. **Add to character**:
   - Append feat to `features_and_traits[]` array
   - Apply any ability score bonuses from feat
   - Apply any proficiency/skill bonuses

### Step 5: Acquire New Features

For each feature in the level's `features` array:

1. **Query feature details**:
   ```bash
   curl -sL "https://www.dnd5eapi.co/api/2014/features/{feature-index}" | jq '{
     name: .name,
     level: .level,
     class: .class.name,
     desc: .desc
   }'
   ```

2. **Add to character**:
   ```json
   {
     "name": "Extra Attack",
     "description": "You can attack twice, instead of once, whenever you take the Attack action on your turn."
   }
   ```

3. **Narrate**: "You gain **{Feature Name}**: {description}"

### Step 6: Spell Progression (if spellcaster)

**Get spell slots for new level**:
```bash
curl -sL "https://www.dnd5eapi.co/api/2014/classes/{class-index}/levels/{level}" | jq '.spellcasting'
```

Returns spell slots by level and spells known/prepared count.

**Update character**:
- Update `spellcasting.spell_slots` with new max and remaining slots
- If prepared caster (Cleric, Druid, Paladin): Update number of spells that can be prepared
- If spells-known caster (Bard, Sorcerer, Ranger): Allow learning new spells

**Learning New Spells**:

1. **Check spells known at this level**: From class level data
2. **Get class spell list**:
   ```bash
   curl -sL "https://www.dnd5eapi.co/api/2014/classes/{class-index}/spells" | jq -r '.results[] | .name'
   ```

3. **Filter by level**: Only show spells of levels the character can cast
4. **Player chooses**: Add to `spellcasting.spells_known[]`
5. **Query spell details** for reference:
   ```bash
   curl -sL "https://www.dnd5eapi.co/api/2014/spells/{spell-index}" | jq '{
     name: .name,
     level: .level,
     school: .school.name,
     casting_time: .casting_time,
     range: .range,
     components: .components,
     duration: .duration,
     desc: .desc
   }'
   ```

**Wizard Spell Learning**:
- Wizards learn 2 spells per level automatically
- Can learn additional spells from scrolls or other spellbooks
- Add to spellbook (not just spells_known)

### Step 7: Update Proficiency Bonus

If proficiency bonus increases (levels 5, 9, 13, 17):

**New proficiency bonuses**:
- Levels 1-4: +2
- Levels 5-8: +3
- Levels 9-12: +4
- Levels 13-16: +5
- Levels 17-20: +6

**Update character**:
- Set `proficiency_bonus` to new value
- Recalculate all skills: `skill_bonus = ability_modifier + proficiency_bonus` (if proficient)
- Recalculate spell save DC: `8 + proficiency_bonus + spellcasting_modifier`
- Recalculate spell attack bonus: `proficiency_bonus + spellcasting_modifier`
- Recalculate weapon attack bonuses: `proficiency_bonus + ability_modifier` (if proficient)

### Step 8: Update Class-Specific Resources

From `class_specific` in level data:

**Barbarian**:
- Rage uses per day
- Rage damage bonus

**Monk**:
- Ki points
- Martial arts die
- Unarmored movement

**Fighter**:
- Action surge uses
- Indomitable uses

**Rogue**:
- Sneak attack dice

**Sorcerer**:
- Sorcery points

**Warlock**:
- Spell slot level
- Invocations known

**Wizard**:
- Spells in spellbook

Update character file with appropriate class resources.

### Step 9: Update Character File

Apply all changes to `{campaign}/characters/{name}.json`:

1. Increment `level`
2. Update `hp.max`, `hp.current`, `hit_dice`
3. Update `ability_scores` and `ability_modifiers` (if ASI taken)
4. Update `proficiency_bonus` (if changed)
5. Update `spellcasting` (slots, spells known)
6. Add new features to `features_and_traits[]`
7. Update class-specific resources
8. Recalculate derived stats (AC, saves, skills, spell DC, attack bonuses)

### Step 10: Narrate Level-Up

Congratulate the player and summarize gains:

> "**Congratulations! {Character} has reached level {level}!**
>
> - HP: {old_max} → {new_max} (+{increase})
> - New Features: {feature_list}
> - Spell Slots: {new_slots}
> - {ASI or Feat if applicable}
>
> You feel the weight of experience settle into your bones. You are stronger, wiser, more capable than before."

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
