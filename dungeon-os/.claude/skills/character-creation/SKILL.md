---
name: Character Creation
description: Guide players through D&D 5e character creation with API-driven validation. Use when creating new characters, validating builds, or calculating derived stats. Ensures characters are rules-compliant with accurate ability bonuses, proficiencies, and starting equipment.
---

# Character Creation

Create validated D&D 5e characters using API data for races, classes, backgrounds, and abilities. This skill guides players through character creation while automatically calculating derived stats.

## DND-API Wrapper

This skill uses the `dnd-api` wrapper for efficient API access with caching:

```bash
# List resources
uv run dnd-api list races
uv run dnd-api list classes

# Get specific resource (cached, fast lookups)
uv run dnd-api get races/elf

# Search for options
uv run dnd-api search classes --name wizard

# Extract minimal fields with jq when needed
uv run dnd-api get races/elf --json | jq '{name, speed, ability_bonuses}'
```

The wrapper caches all API responses for speed and token efficiency. All examples below can use either the wrapper or direct curl commands.

## Character Creation Workflow

When a player wants to create a new character, follow this guided workflow:

### Step 1: Choose Race

1. **List available races**:
   ```bash
   curl -sL "https://www.dnd5eapi.co/api/2014/races" | jq -r '.results[] | "- \(.name) (\(.index))"'
   ```

2. **Player selects race**, then fetch details:
   ```bash
   curl -sL "https://www.dnd5eapi.co/api/2014/races/{race-index}" | jq '{
     name: .name,
     speed: .speed,
     ability_bonuses: .ability_bonuses,
     size: .size,
     languages: .languages,
     traits: .traits
   }'
   ```

3. **Check for subraces** (Elf, Dwarf, Halfling, Gnome have subraces):
   ```bash
   curl -sL "https://www.dnd5eapi.co/api/2014/races/{race-index}/subraces" | jq -r '.results[] | "- \(.name) (\(.index))"'
   ```

   If subraces exist, player chooses one:
   ```bash
   curl -sL "https://www.dnd5eapi.co/api/2014/subraces/{subrace-index}" | jq '{
     name: .name,
     desc: .desc,
     ability_bonuses: .ability_bonuses,
     racial_traits: .racial_traits
   }'
   ```

4. **Fetch racial traits** (if player wants details):
   ```bash
   curl -sL "https://www.dnd5eapi.co/api/2014/traits/{trait-index}" | jq '{
     name: .name,
     desc: .desc
   }'
   ```

5. **Record**: Note race, subrace (if any), ability bonuses, speed, languages, traits

### Step 2: Choose Class

1. **List available classes**:
   ```bash
   curl -sL "https://www.dnd5eapi.co/api/2014/classes" | jq -r '.results[] | "- \(.name) (\(.index))"'
   ```

2. **Player selects class**, then fetch details:
   ```bash
   curl -sL "https://www.dnd5eapi.co/api/2014/classes/{class-index}" | jq '{
     name: .name,
     hit_die: .hit_die,
     proficiency_choices: .proficiency_choices,
     proficiencies: .proficiencies,
     saving_throws: .saving_throws,
     starting_equipment: .starting_equipment,
     starting_equipment_options: .starting_equipment_options
   }'
   ```

3. **Get spellcasting info** (if applicable):
   ```bash
   curl -sL "https://www.dnd5eapi.co/api/2014/classes/{class-index}/spellcasting" | jq '{
     spellcasting_ability: .spellcasting_ability.name,
     info: .info
   }'
   ```

4. **Player chooses skill proficiencies**:
   - Class provides proficiency_choices (e.g., "Choose 2 from Arcana, History, Insight...")
   - Query each skill for description if needed:
   ```bash
   curl -sL "https://www.dnd5eapi.co/api/2014/skills/{skill-index}" | jq '{
     name: .name,
     desc: .desc,
     ability_score: .ability_score.name
   }'
   ```

5. **Record**: Class, hit die, proficiencies, saving throws, spellcasting ability

### Step 3: Choose Background

1. **List available backgrounds**:
   ```bash
   curl -sL "https://www.dnd5eapi.co/api/2014/backgrounds" | jq -r '.results[] | "- \(.name) (\(.index))"'
   ```

2. **Player selects background**, then fetch details:
   ```bash
   curl -sL "https://www.dnd5eapi.co/api/2014/backgrounds/{background-index}" | jq '{
     name: .name,
     starting_proficiencies: .starting_proficiencies,
     language_options: .language_options,
     starting_equipment: .starting_equipment,
     feature: .feature
   }'
   ```

3. **Record**: Background, additional proficiencies, languages, equipment, feature

### Step 4: Determine Ability Scores

Offer player choice of method:

**Standard Array**: 15, 14, 13, 12, 10, 8 (assign to abilities)
**Point Buy**: 27 points to distribute (8=0, 9=1, 10=2, 11=3, 12=4, 13=5, 14=7, 15=9)
**Rolling**: Roll 4d6 drop lowest, 6 times:
```bash
source .venv/bin/activate && roll 4d6kh3 -v
```
(Repeat 6 times, record results)

1. **Player assigns scores** to STR, DEX, CON, INT, WIS, CHA

2. **Apply racial bonuses**:
   - Base racial bonuses (e.g., Elf +2 DEX)
   - Subrace bonuses (e.g., High Elf +1 INT)
   - Record final ability scores

3. **Calculate modifiers**:
   ```
   modifier = floor((ability_score - 10) / 2)
   ```

4. **Query ability score info** (optional, for player reference):
   ```bash
   curl -sL "https://www.dnd5eapi.co/api/2014/ability-scores/{ability-index}" | jq '{
     name: .name,
     full_name: .full_name,
     desc: .desc,
     skills: .skills
   }'
   ```
   Ability indexes: `str`, `dex`, `con`, `int`, `wis`, `cha`

### Step 5: Calculate Derived Stats

**Hit Points**:
- Level 1 HP = hit_die_max + CON modifier
- Example: Fighter (d10) with CON 14 (+2) = 10 + 2 = 12 HP

**Armor Class**:
- Unarmored: 10 + DEX modifier
- With armor: Use armor's base AC + DEX modifier (if allowed)
- Example: Leather armor (AC 11) with DEX 14 (+2) = 13 AC

**Proficiency Bonus**:
- Level 1-4: +2
- Level 5-8: +3
- Level 9-12: +4
- Level 13-16: +5
- Level 17-20: +6

**Initiative**:
- initiative = DEX modifier

**Skill Bonuses**:
- If proficient: ability_modifier + proficiency_bonus
- If not proficient: ability_modifier
- Expertise (if applicable): ability_modifier + (proficiency_bonus × 2)

**Saving Throws**:
- Proficient saves: ability_modifier + proficiency_bonus
- Non-proficient saves: ability_modifier

**Spell Save DC** (if spellcaster):
- spell_save_dc = 8 + proficiency_bonus + spellcasting_ability_modifier

**Spell Attack Bonus** (if spellcaster):
- spell_attack_bonus = proficiency_bonus + spellcasting_ability_modifier

### Step 6: Starting Equipment

1. **Class starting equipment**:
   - Use API data from class query
   - Player makes choices from equipment options

2. **Background starting equipment**:
   - Use API data from background query

3. **Query equipment details** as needed:
   ```bash
   curl -sL "https://www.dnd5eapi.co/api/2014/equipment/{equipment-index}" | jq '{
     name: .name,
     equipment_category: .equipment_category.name,
     cost: .cost,
     weight: .weight,
     armor_class: .armor_class,
     damage: .damage,
     properties: .properties
   }'
   ```

4. **Calculate starting gold** (if using gold instead of equipment):
   - Consult class starting gold table
   - Or use standard equipment packages

### Step 7: Choose Starting Spells (if spellcaster)

1. **Get class spell list**:
   ```bash
   curl -sL "https://www.dnd5eapi.co/api/2014/classes/{class-index}/spells" | jq -r '.results[] | .name'
   ```

2. **Player chooses cantrips and spells** (consult class rules for number):
   - Wizard: 3 cantrips + 6 level-1 spells in spellbook
   - Cleric: All cleric spells available, prepare WIS_modifier + level spells
   - Sorcerer: 4 cantrips + 2 level-1 spells known

3. **Query spell details**:
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

4. **Set spell slots**:
   - Level 1 full casters: 2 level-1 slots
   - Level 1 half casters: No slots yet
   - Warlock: Different slot progression

### Step 8: Personality & Flavor

Guide player through:
- **Personality traits** (2): How does character behave?
- **Ideals** (1): What drives character?
- **Bonds** (1): Who/what matters most?
- **Flaws** (1): What's character's weakness?

Backgrounds often provide tables to roll on:
```bash
source .venv/bin/activate && roll 1d8 -v
```

### Step 9: Generate Character File

Create character file at `{campaign}/characters/{character-name}.json`:

```json
{
  "name": "Eldrin Stormwind",
  "controlled_by": "player-123",
  "race": "High Elf",
  "class": "Wizard",
  "level": 1,
  "background": "Sage",
  "alignment": "Neutral Good",
  "experience_points": 0,
  "ability_scores": {
    "strength": 8,
    "dexterity": 14,
    "constitution": 13,
    "intelligence": 17,
    "wisdom": 12,
    "charisma": 10
  },
  "ability_modifiers": {
    "strength": -1,
    "dexterity": 2,
    "constitution": 1,
    "intelligence": 3,
    "wisdom": 1,
    "charisma": 0
  },
  "proficiency_bonus": 2,
  "skills": {
    "arcana": 5,
    "history": 5,
    "investigation": 5,
    "perception": 1
  },
  "hp": {
    "current": 7,
    "max": 7,
    "temp": 0
  },
  "armor_class": 12,
  "initiative": 2,
  "speed": 30,
  "hit_dice": {
    "total": 1,
    "remaining": 1
  },
  "death_saves": {
    "successes": 0,
    "failures": 0
  },
  "inventory": [
    {"name": "Spellbook", "quantity": 1, "weight": 3, "description": "Contains your wizard spells"},
    {"name": "Component Pouch", "quantity": 1, "weight": 2, "description": "For spell components"},
    {"name": "Scholar's Pack", "quantity": 1, "weight": 10, "description": "Backpack, book, ink, pen, parchment, etc."}
  ],
  "weapons": [
    {
      "name": "Quarterstaff",
      "attack_bonus": 1,
      "damage": "1d6-1",
      "damage_type": "bludgeoning",
      "properties": ["versatile"],
      "equipped": true
    }
  ],
  "armor": {
    "name": "None",
    "ac_bonus": 0,
    "type": "light",
    "equipped": false
  },
  "spellcasting": {
    "ability": "intelligence",
    "spell_save_dc": 13,
    "spell_attack_bonus": 5,
    "spell_slots": {
      "1": {"max": 2, "remaining": 2}
    },
    "spells_known": [
      "fire-bolt",
      "light",
      "mage-hand",
      "burning-hands",
      "detect-magic",
      "mage-armor",
      "magic-missile",
      "shield",
      "identify"
    ]
  },
  "features_and_traits": [
    {
      "name": "Darkvision",
      "description": "You can see in dim light within 60 feet as if it were bright light, and in darkness as if it were dim light."
    },
    {
      "name": "Fey Ancestry",
      "description": "You have advantage on saving throws against being charmed, and magic can't put you to sleep."
    },
    {
      "name": "Trance",
      "description": "Elves don't need to sleep. Instead, they meditate deeply for 4 hours a day."
    },
    {
      "name": "Arcane Recovery",
      "description": "Once per day when you finish a short rest, you can recover spent spell slots with a combined level equal to or less than half your wizard level (rounded up)."
    },
    {
      "name": "Researcher (Background Feature)",
      "description": "When you attempt to learn or recall a piece of lore, if you do not know that information, you often know where and from whom you can obtain it."
    }
  ],
  "personality_traits": "I use polysyllabic words to convey the impression of great erudition. I'm convinced that people are always trying to steal my secrets.",
  "ideals": "Knowledge. The path to power and self-improvement is through knowledge.",
  "bonds": "I have an ancient text that holds terrible secrets that must not fall into the wrong hands.",
  "flaws": "Unlocking an ancient mystery is worth the price of a civilization."
}
```

### Step 10: Register Character

1. **Add to campaign state**:
   - Update `{campaign}/state.json`
   - Add character to `party_members` array

2. **Associate with player**:
   - Check/update `{campaign}/players/{player-id}.json`
   - Add character to player's `characters` array

3. **Announce**: "**{Character Name} has joined the party!** Welcome, {race} {class}."

## Validation Checklist

Before finalizing character:

- [ ] All required fields populated
- [ ] Ability scores in valid range (3-20 at level 1, after racial bonuses)
- [ ] Skill proficiencies match class + background (no duplicates)
- [ ] Starting equipment chosen from class + background options
- [ ] Spells known/prepared within class limits
- [ ] HP calculated correctly (hit_die_max + CON_modifier)
- [ ] AC calculated correctly (armor + DEX_modifier)
- [ ] Spell save DC = 8 + proficiency + spellcasting_modifier
- [ ] Spell attack = proficiency + spellcasting_modifier
- [ ] Proficiency bonus = 2 (level 1)
- [ ] Hit dice = 1d{hit_die} (1 remaining)

## Common Character Builds (Quick Reference)

### Human Fighter

- Race: Human (+1 all abilities)
- Class: Fighter (d10 hit die)
- Proficiencies: All armor, all weapons, STR & CON saves
- Fighting Style: Choose at level 1
- Second Wind: Self-heal as bonus action

### High Elf Wizard

- Race: High Elf (+2 DEX, +1 INT)
- Class: Wizard (d6 hit die)
- Proficiencies: Daggers, darts, slings, quarterstaffs, light crossbows, INT & WIS saves
- Spellcasting: Intelligence-based
- Spellbook: 6 level-1 spells

### Hill Dwarf Cleric

- Race: Hill Dwarf (+2 CON, +1 WIS, +1 HP per level)
- Class: Cleric (d8 hit die)
- Proficiencies: Light/medium armor, shields, simple weapons, WIS & CHA saves
- Spellcasting: Wisdom-based, prepare spells daily
- Divine Domain: Choose at level 1

### Halfling Rogue

- Race: Lightfoot Halfling (+2 DEX, +1 CHA)
- Class: Rogue (d8 hit die)
- Proficiencies: Light armor, simple weapons, hand crossbows, longswords, rapiers, shortswords, thieves' tools, DEX & INT saves
- Expertise: Double proficiency bonus for 2 skills
- Sneak Attack: Extra damage when you have advantage

## API Endpoints Reference

**Races**:
- List: `GET /api/2014/races`
- Details: `GET /api/2014/races/{index}`
- Subraces: `GET /api/2014/races/{index}/subraces`
- Traits: `GET /api/2014/races/{index}/traits`

**Classes**:
- List: `GET /api/2014/classes`
- Details: `GET /api/2014/classes/{index}`
- Spellcasting: `GET /api/2014/classes/{index}/spellcasting`
- Proficiencies: `GET /api/2014/classes/{index}/proficiencies`
- Spell List: `GET /api/2014/classes/{index}/spells`

**Backgrounds**:
- List: `GET /api/2014/backgrounds`
- Details: `GET /api/2014/backgrounds/{index}`

**Abilities**:
- List: `GET /api/2014/ability-scores`
- Details: `GET /api/2014/ability-scores/{index}`

**Skills**:
- List: `GET /api/2014/skills`
- Details: `GET /api/2014/skills/{index}`

**Proficiencies**:
- List: `GET /api/2014/proficiencies`
- Details: `GET /api/2014/proficiencies/{index}`

**Equipment**:
- List: `GET /api/2014/equipment`
- Details: `GET /api/2014/equipment/{index}`

**Spells**:
- List: `GET /api/2014/spells`
- Details: `GET /api/2014/spells/{index}`

## Tips

- **Let players lead**: Ask questions, don't rush them through choices
- **Explain trade-offs**: "Wizards are powerful spellcasters but fragile in melee"
- **Show API data**: Present race/class features directly from API so players understand exactly what they're getting
- **Validate as you go**: Check for errors at each step, not at the end
- **Save incrementally**: Can save partial character and resume later if needed
- **Offer guidance**: New players appreciate suggestions ("Dexterity is important for Rogues")
- **Be flexible**: If player has a concept that's unusual, work with them to make it fit

## Common Mistakes to Avoid

- **Don't skip API queries**: Always fetch race/class data, don't assume you know it
- **Don't forget racial bonuses**: Apply them AFTER player assigns base scores
- **Don't confuse proficiency choices with automatic proficiencies**: Players must choose skills from the provided list
- **Don't give too many starting spells**: Check class rules for exact number
- **Don't forget background equipment**: It's easy to overlook
- **Don't use deprecated stat blocks**: Always use API data for current rules

## Integration with Other Skills

- **After creation** → Use worldbuilding skill to establish character's backstory connections to the world
- **In session 0** → Create all party members' characters together
- **During play** → Character advancement skill handles leveling up
- **Combat setup** → Combat skill reads these character files for stats
