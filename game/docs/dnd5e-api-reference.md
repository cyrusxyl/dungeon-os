# D&D 5e API Reference

Every endpoint below also works with the wrapper, which caches it and keeps the answer short:
`uv run dnd-cli get <endpoint> --fields a,b`. The curl forms are for people, not for the DM: on the visual stage, curl stops the game for a permission prompt.


DungeonOS integrates with the D&D 5e API at `https://www.dnd5eapi.co/api/2014/` to provide validated rules data. All 47 endpoints are documented below with example usage.

### API Usage Pattern

```bash
curl -sL "https://www.dnd5eapi.co/api/2014/{endpoint}/{index}" | jq '{fields}'
```

**Always use `-sL` flags**: Silent mode, follow redirects
**Always pipe to `jq`**: Parse and format JSON output

### Character Creation Endpoints (10)

Used by: `character-creation` skill

#### Races
```bash
# List all races
curl -sL "https://www.dnd5eapi.co/api/2014/races" | jq -r '.results[] | .name'

# Get race details
curl -sL "https://www.dnd5eapi.co/api/2014/races/elf" | jq '{
  name, speed, ability_bonuses, size, languages, traits
}'

# Get subraces for a race
curl -sL "https://www.dnd5eapi.co/api/2014/races/elf/subraces" | jq

# Get specific subrace
curl -sL "https://www.dnd5eapi.co/api/2014/subraces/high-elf" | jq

# Get racial traits
curl -sL "https://www.dnd5eapi.co/api/2014/traits/darkvision" | jq
```

#### Classes
```bash
# List all classes
curl -sL "https://www.dnd5eapi.co/api/2014/classes" | jq -r '.results[] | .name'

# Get class details
curl -sL "https://www.dnd5eapi.co/api/2014/classes/wizard" | jq '{
  name, hit_die, proficiencies, saving_throws, starting_equipment
}'

# Get class proficiencies
curl -sL "https://www.dnd5eapi.co/api/2014/classes/wizard/proficiencies" | jq

# Get class spellcasting info
curl -sL "https://www.dnd5eapi.co/api/2014/classes/wizard/spellcasting" | jq

# Get subclasses
curl -sL "https://www.dnd5eapi.co/api/2014/classes/wizard/subclasses" | jq

# Get specific subclass
curl -sL "https://www.dnd5eapi.co/api/2014/subclasses/evocation" | jq
```

#### Backgrounds
```bash
# List all backgrounds
curl -sL "https://www.dnd5eapi.co/api/2014/backgrounds" | jq

# Get background details
curl -sL "https://www.dnd5eapi.co/api/2014/backgrounds/sage" | jq
```

#### Ability Scores & Skills
```bash
# List all ability scores
curl -sL "https://www.dnd5eapi.co/api/2014/ability-scores" | jq

# Get ability details
curl -sL "https://www.dnd5eapi.co/api/2014/ability-scores/str" | jq '{
  name, full_name, desc, skills
}'

# List all skills
curl -sL "https://www.dnd5eapi.co/api/2014/skills" | jq

# Get skill details
curl -sL "https://www.dnd5eapi.co/api/2014/skills/stealth" | jq '{
  name, desc, ability_score
}'
```

#### Proficiencies
```bash
# List all proficiencies
curl -sL "https://www.dnd5eapi.co/api/2014/proficiencies" | jq

# Get proficiency details
curl -sL "https://www.dnd5eapi.co/api/2014/proficiencies/light-armor" | jq
```

### Equipment Endpoints (3)

Used by: `worldbuilding` skill

```bash
# List all equipment
curl -sL "https://www.dnd5eapi.co/api/2014/equipment" | jq

# Get equipment details (weapon)
curl -sL "https://www.dnd5eapi.co/api/2014/equipment/longsword" | jq '{
  name, cost, damage, properties, weight
}'

# Get equipment details (armor)
curl -sL "https://www.dnd5eapi.co/api/2014/equipment/chain-mail" | jq '{
  name, cost, armor_class, armor_category, stealth_disadvantage
}'

# Browse equipment by category
curl -sL "https://www.dnd5eapi.co/api/2014/equipment-categories/weapon" | jq '.equipment[] | .name'

# Get weapon property details
curl -sL "https://www.dnd5eapi.co/api/2014/weapon-properties/finesse" | jq '{
  name, desc
}'
```

### Combat Endpoints (2)

Used by: `combat` skill

```bash
# List all conditions
curl -sL "https://www.dnd5eapi.co/api/2014/conditions" | jq

# Get condition details
curl -sL "https://www.dnd5eapi.co/api/2014/conditions/paralyzed" | jq '{
  name, desc
}'

# List all damage types
curl -sL "https://www.dnd5eapi.co/api/2014/damage-types" | jq

# Get damage type details
curl -sL "https://www.dnd5eapi.co/api/2014/damage-types/fire" | jq '{
  name, desc
}'
```

### Character Advancement Endpoints (13)

Used by: `character-advancement` skill

```bash
# List all class levels
curl -sL "https://www.dnd5eapi.co/api/2014/classes/fighter/levels" | jq

# Get specific level details
curl -sL "https://www.dnd5eapi.co/api/2014/classes/fighter/levels/5" | jq '{
  level, ability_score_bonuses, prof_bonus, features, spellcasting, class_specific
}'

# Get features for a level
curl -sL "https://www.dnd5eapi.co/api/2014/classes/fighter/levels/5/features" | jq

# Get specific feature details
curl -sL "https://www.dnd5eapi.co/api/2014/features/extra-attack" | jq '{
  name, level, class, desc
}'

# List all feats
curl -sL "https://www.dnd5eapi.co/api/2014/feats" | jq

# Get feat details
curl -sL "https://www.dnd5eapi.co/api/2014/feats/grappler" | jq '{
  name, desc, prerequisites
}'
```

### Magic System Endpoints (7)

Used by: `magic` skill

```bash
# List all spells
curl -sL "https://www.dnd5eapi.co/api/2014/spells" | jq

# Filter spells by level
curl -sL "https://www.dnd5eapi.co/api/2014/spells?level=1" | jq

# Get spell details
curl -sL "https://www.dnd5eapi.co/api/2014/spells/fireball" | jq '{
  name, level, school, casting_time, range, components, duration,
  concentration, ritual, attack_type, dc, damage, desc, higher_level
}'

# Get class spell list
curl -sL "https://www.dnd5eapi.co/api/2014/classes/wizard/spells" | jq -r '.results[] | .name'

# List all magic schools
curl -sL "https://www.dnd5eapi.co/api/2014/magic-schools" | jq

# Get magic school details
curl -sL "https://www.dnd5eapi.co/api/2014/magic-schools/evocation" | jq '{
  name, desc
}'

# List magic items (for loot generation)
curl -sL "https://www.dnd5eapi.co/api/2014/magic-items" | jq

# Get magic item details
curl -sL "https://www.dnd5eapi.co/api/2014/magic-items/adamantine-armor" | jq
```

### Exploration Endpoints (2)

Used by: `exploration` skill

```bash
# Already covered above: skills and ability-scores
# Skills: perception, investigation, survival, stealth, etc.
# Abilities: Used for raw ability checks
```

### Social Interaction Endpoints (2)

Used by: `social` skill

```bash
# List all languages
curl -sL "https://www.dnd5eapi.co/api/2014/languages" | jq

# Get language details
curl -sL "https://www.dnd5eapi.co/api/2014/languages/elvish" | jq '{
  name, desc, type, typical_speakers, script
}'

# Social skills (already covered in skills endpoint):
# - persuasion, deception, intimidation, insight, performance
```

### Monster & NPC Endpoints (1)

Used by: `combat` and `worldbuilding` skills

```bash
# List all monsters
curl -sL "https://www.dnd5eapi.co/api/2014/monsters" | jq

# Get monster details
curl -sL "https://www.dnd5eapi.co/api/2014/monsters/goblin" | jq '{
  name, type, hit_points, armor_class, challenge_rating,
  strength, dexterity, constitution, intelligence, wisdom, charisma,
  actions, special_abilities
}'
```

### Rules Reference Endpoints (2)

Used for: Rules clarification

```bash
# List all rule sections
curl -sL "https://www.dnd5eapi.co/api/2014/rule-sections" | jq

# Get specific rule section
curl -sL "https://www.dnd5eapi.co/api/2014/rule-sections/combat" | jq

# List all rules
curl -sL "https://www.dnd5eapi.co/api/2014/rules" | jq

# Get specific rule
curl -sL "https://www.dnd5eapi.co/api/2014/rules/adventuring" | jq
```

### Other Endpoints (5)

```bash
# Alignments
curl -sL "https://www.dnd5eapi.co/api/2014/alignments" | jq
curl -sL "https://www.dnd5eapi.co/api/2014/alignments/lawful-good" | jq

# Starting equipment options
curl -sL "https://www.dnd5eapi.co/api/2014/starting-equipment/{class}" | jq

# Character level progression (already covered in class levels)
```

### API Coverage Summary

**Total endpoints**: 47

**By category**:
- Character creation: 10 (races, subraces, classes, subclasses, backgrounds, abilities, skills, proficiencies, traits)
- Equipment: 3 (equipment, equipment-categories, weapon-properties)
- Combat: 2 (conditions, damage-types)
- Advancement: 13 (class levels, level features, features, feats, starting-equipment)
- Magic: 7 (spells, class spells, magic-schools, magic-items)
- Monsters: 1 (monsters)
- Social: 2 (languages, skills)
- Rules: 2 (rules, rule-sections)
- Other: 7 (alignments, ability-scores, proficiencies)

### When to Use Each Endpoint

| Situation | Endpoint | Skill |
|-----------|----------|-------|
| Creating new character | `/races`, `/classes`, `/backgrounds` | character-creation |
| Character levels up | `/classes/{class}/levels/{level}` | character-advancement |
| Learning new spell | `/classes/{class}/spells`, `/spells/{spell}` | character-advancement, magic |
| Casting spell | `/spells/{spell}` | magic |
| Spell applies condition | `/conditions/{condition}` | combat |
| Looking up weapon stats | `/equipment/{weapon}` | worldbuilding |
| Need monster for encounter | `/monsters/{monster}` | combat, worldbuilding |
| Skill check needed | `/skills/{skill}` | exploration, social |
| NPC speaks different language | `/languages/{language}` | social |
| Player takes feat | `/feats/{feat}` | character-advancement |
| Need to clarify rule | `/rules`, `/rule-sections` | any |

### API Best Practices

1. **Always query, never guess**: If you need spell damage, weapon stats, or condition effects, query the API
2. **Cache in campaign files**: Save fetched monster/NPC stats to campaign files for reuse
3. **Show API data to players**: Let them see exact spell descriptions, feat requirements, etc.
4. **Handle failures gracefully**: If API is down, fall back to manual lookup with player approval
5. **Use jq for filtering**: Extract only needed fields to keep output clean
6. **Validate with schemas**: Ensure generated character/NPC files match schemas

### Common API Patterns

**List all resources**:
```bash
curl -sL "https://www.dnd5eapi.co/api/2014/{resource}" | jq -r '.results[] | .name'
```

**Get specific resource**:
```bash
curl -sL "https://www.dnd5eapi.co/api/2014/{resource}/{index}" | jq
```

**Filter nested resources**:
```bash
curl -sL "https://www.dnd5eapi.co/api/2014/classes/wizard/spells" | jq -r '.results[] | .name'
```

**Extract specific fields**:
```bash
curl -sL "https://www.dnd5eapi.co/api/2014/monsters/goblin" | jq '{name, hp: .hit_points, ac: .armor_class[0].value}'
```
