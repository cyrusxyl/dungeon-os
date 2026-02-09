---
name: Magic & Spellcasting
description: Handle D&D 5e spellcasting mechanics including spell selection, slot management, concentration, ritual casting, and spell scrolls. Use when characters cast spells, learn new spells, or interact with magical effects. Validates spell requirements and tracks resources.
---

# Magic & Spellcasting

Manage all aspects of D&D 5e magic with API-sourced spell data, slot tracking, and spellcasting rules enforcement.

## Casting a Spell

When a player casts a spell:

### Step 1: Query Spell Details

```bash
# Full spell data (cached)
uv run dnd-cli get spells/{spell-index}

# Or extract specific fields with jq
uv run dnd-cli get spells/{spell-index} --json | jq '{
  name: .name,
  level: .level,
  school: .school.name,
  casting_time: .casting_time,
  range: .range,
  components: .components,
  material: .material,
  duration: .duration,
  concentration: .concentration,
  ritual: .ritual,
  attack_type: .attack_type,
  dc: .dc,
  damage: .damage,
  desc: .desc,
  higher_level: .higher_level
}'

# Search for spells by criteria
uv run dnd-cli search spells --level 3 --school evocation
```

Key fields:
- **level**: 0 (cantrip) through 9
- **school**: Abjuration, Conjuration, Divination, Enchantment, Evocation, Illusion, Necromancy, Transmutation
- **components**: V (verbal), S (somatic), M (material)
- **concentration**: true/false
- **ritual**: true/false
- **attack_type**: "SPELL" (spell attack) or null (save/no attack)
- **dc**: Save type if applicable

### Step 2: Verify Requirements

**Check spell is known/prepared**:
- Read character's `spellcasting.spells_known[]`
- For prepared casters (Cleric, Druid), check daily prepared list

**Check components**:
- **V (Verbal)**: Can't cast if silenced or in *Silence* spell
- **S (Somatic)**: Can't cast if hands are bound or holding shield (unless War Caster feat)
- **M (Material)**: Need component pouch or specific material
  - If material has cost (e.g., "diamond worth 300 gp"), must have exact material
  - Component pouch covers materials without specified cost

**Check spell slots** (if level > 0):
- Read `spellcasting.spell_slots["{level}"].remaining`
- If 0: "You're out of level {level} spell slots!"
- Cantrips (level 0): Unlimited, no slot required

**Check range**:
- Self: Affects only caster
- Touch: Must be within 5 feet
- Ranged: Must be within specified range (e.g., 120 feet)
- Check for cover and line of sight

### Step 3: Deduct Spell Slot

If casting at base level:
- Decrement `spell_slots["{level}"].remaining` by 1

If casting at higher level (upcasting):
- Player chooses higher spell slot
- Decrement chosen level's remaining slots
- Apply higher-level effects from `higher_level` field

**Update character file immediately**.

### Step 4: Resolve Spell Effect

**Spell Attack Roll** (if `attack_type: "SPELL"`):
1. Roll attack: 1d20 + spell_attack_bonus
   ```bash
   source .venv/bin/activate && roll 1d20+{spell_attack_bonus} -v
   ```
2. Compare to target AC
3. On hit: Roll damage

**Saving Throw** (if has `dc`):
1. Target rolls: 1d20 + ability_modifier
   ```bash
   source .venv/bin/activate && roll 1d20+{modifier} -v
   ```
   Use ability from `dc.dc_type.name` (e.g., DEX, WIS)
2. Compare to caster's `spell_save_dc`
3. On failure: Apply full effect/damage
4. On success: Usually half damage or no effect

**Damage** (if applicable):
1. Parse damage from `damage` field (e.g., "8d6")
2. Roll damage:
   ```bash
   source .venv/bin/activate && roll 8d6 -v
   ```
3. Apply to target(s)
4. If upcasted, add extra damage from `higher_level`

**No Attack/Save** (buff, utility, etc.):
- Apply effect as described
- Track duration if applicable

### Step 5: Handle Concentration

If `concentration: true`:

1. **Check existing concentration**: Can only concentrate on one spell at a time
   - If already concentrating: Choosing to concentrate on new spell ends previous one
   - Update state: Remove old concentration spell/effect

2. **Track concentration**:
   - Add to character state or `active_encounter.conditions`
   - Note spell name, duration, and effect

3. **Concentration checks** (when caster takes damage):
   - DC = 10 or half damage taken, whichever is higher
   - Roll CON save
   - On failure: Concentration breaks, spell ends

4. **End concentration**:
   - Remove spell effect
   - Update state

### Step 6: Track Duration

**Instantaneous**: Effect happens immediately, no tracking

**Concentration, up to X**: Lasts up to maximum duration or until concentration breaks
- Example: "Concentration, up to 1 minute" = max 10 rounds

**X minutes/hours/days**: Lasts specified time
- 1 minute = 10 rounds
- Track rounds/time in state

**Until dispelled**: Lasts until *Dispel Magic* or similar effect removes it

**Permanent**: Lasts forever (rare)

### Step 7: Narrate Casting

**Cantrip example**:
> "You point at the goblin and speak the incantation. A bolt of fire streaks from your fingertip (**Fire Bolt**). Roll to hit!"

**Leveled spell with slot expenditure**:
> "You weave the complex gestures and intone the words of power, feeling your magic flow out (**Fireball, 3rd-level slot**). The bead of fire streaks to the center of the room..."

## Ritual Casting

If `ritual: true` and character has Ritual Caster feature:

**Requirements**:
- Spell must be prepared/known (for some classes)
- Takes 10 minutes longer to cast
- **No spell slot required**

**Process**:
1. Verify spell is ritual-eligible
2. Add 10 minutes to casting time
3. Cast spell normally but don't deduct spell slot

**Classes with ritual casting**:
- Bard: Can ritual cast known spells
- Cleric: Can ritual cast prepared spells
- Druid: Can ritual cast prepared spells
- Wizard: Can ritual cast spells in spellbook (don't need to be prepared)

**Example rituals**: *Detect Magic*, *Identify*, *Find Familiar*, *Alarm*, *Comprehend Languages*

## Spell Selection & Learning

### Learning Spells on Level-Up

See Character Advancement skill for detailed workflow.

**Quick reference**:
1. Check class level data for spells known/prepared at new level
2. Query class spell list:
   ```bash
   # Get class spell list (cached)
   uv run dnd-cli get classes/{class-index}/spells --json | jq -r '.results[] | .name'
   ```
3. Filter by levels character can cast
4. Player chooses, add to character

### Wizard Learning Spells from Scrolls

When a wizard finds a spell scroll:

1. **Check spell level**: Must be a wizard spell of level wizard can cast
2. **Time required**: 2 hours per spell level
3. **Cost**: 50 gp per spell level (for ink and materials)
4. **Roll Arcana check** (if spell level > wizard level):
   - DC = 10 + spell level
   - On success: Spell copied to spellbook
   - On failure: Cannot attempt again, scroll intact

5. **Add to spellbook**: Add to character's `spellcasting.spells_known[]` or separate spellbook tracking

### Preparing Spells (Cleric, Druid, Paladin, Wizard)

Each long rest, prepared casters can change their prepared spell list:

**Number of spells prepared**: Spellcasting ability modifier + class level (minimum 1)
- Example: Cleric with WIS 16 (+3), level 5 = 3 + 5 = 8 spells prepared

**Process**:
1. Calculate number allowed
2. Player chooses from their known/available spells
3. Update character file with prepared list (if tracking separately from spells_known)

**Wizards**: Prepare from spellbook
**Clerics/Druids**: Prepare from entire class spell list
**Paladins**: Prepare from paladin spell list

## Spell Scrolls

When a character uses a spell scroll:

### Reading the Scroll

**Requirements**:
- Spell must be on your class spell list
- If spell level > your max spell level: Make ability check
  - DC = 10 + spell level
  - Use spellcasting ability
  - On failure: Scroll is destroyed, spell fails

**Casting from scroll**:
- Use scroll's spell save DC and attack bonus (usually DC 13, +5 attack)
- OR use your own if higher
- Casting time as per spell
- Scroll is consumed after use

### Identifying Scrolls

**Action**: Arcana check or *Identify* spell

**Arcana DC**: 10 + spell level

**Result**: Learn spell name and level

## Spellcasting Focus

Alternative to component pouch:

**Arcane Focus** (Wizard, Sorcerer, Warlock):
- Wand, orb, staff, crystal, rod
- Replaces material components without cost

**Holy Symbol** (Cleric, Paladin):
- Amulet or emblem
- Can be on shield

**Druidic Focus** (Druid):
- Sprig of mistletoe, totem, wooden staff, yew wand

**Must hold in hand** to use (unless on shield for holy symbol).

## Counterspell & Spell Identification

### Counterspell

When a creature casts a spell, another caster can use reaction:

1. **Cast Counterspell** (reaction, 3rd-level spell)
2. If target spell is 3rd-level or lower: Automatically countered
3. If target spell is 4th-level or higher:
   - Make spellcasting ability check
   - DC = 10 + target spell level
   - On success: Spell countered
   - On failure: Spell proceeds

### Identifying Spells Being Cast

**Reaction**: Make Arcana check

**DC**: 15 + spell level

**On success**: Identify spell being cast

## Spell Schools

Query school information:

```bash
curl -sL "https://www.dnd5eapi.co/api/2014/magic-schools/{school-index}" | jq '{
  name: .name,
  desc: .desc
}'
```

**Schools**:
- **Abjuration**: Protection, wards (*Shield*, *Counterspell*)
- **Conjuration**: Summon, teleport (*Misty Step*, *Conjure Animals*)
- **Divination**: Reveal information (*Detect Magic*, *Scrying*)
- **Enchantment**: Charm, control minds (*Charm Person*, *Hold Person*)
- **Evocation**: Raw energy, damage (*Fireball*, *Lightning Bolt*)
- **Illusion**: Deceive senses (*Disguise Self*, *Invisibility*)
- **Necromancy**: Life and death (*Animate Dead*, *Revivify*)
- **Transmutation**: Transform (*Polymorph*, *Haste*)

Some class features interact with schools (e.g., Abjuration Wizard, Evocation Wizard).

## Spell Slot Recovery

**Short Rest**:
- Warlock: Recover all spell slots
- Wizard: Arcane Recovery (once per day, recover slots = half wizard level rounded up)

**Long Rest**:
- All classes: Recover all spell slots

**Update character file** after rest.

## Common Spell Scenarios

### Area of Effect Spells

**Fireball** (20-foot radius):
1. Player chooses center point within range
2. All creatures in area make DEX save vs caster's DC
3. Roll damage once: 8d6 fire
4. Failed save: Full damage
5. Successful save: Half damage (rounded down)

### Healing Spells

**Cure Wounds** (1st-level):
1. Touch target
2. Roll 1d8 + spellcasting modifier
3. Add HP to target (can't exceed max)
4. Update target's character file

### Buff Spells

**Bless** (1st-level, concentration, 1 minute):
1. Choose up to 3 creatures
2. They add 1d4 to attack rolls and saves
3. Track concentration on caster
4. Roll 1d4 each time blessed creature makes attack/save

### Summoning Spells

**Conjure Animals** (3rd-level, concentration, 1 hour):
1. Choose CR and number (CR 2 = 1 beast, CR 1 = 2 beasts, etc.)
2. Query beast stats from API
3. Create temporary NPC files for summoned creatures
4. Creatures act on caster's turn
5. When concentration ends, creatures disappear

## Spell Lists by Class

Get complete class spell list:

```bash
# Get class spell list (cached)
uv run dnd-cli get classes/{class-index}/spells --json | jq -r '.results[] | .name'
```

**Classes**:
- `bard`, `cleric`, `druid`, `paladin`, `ranger`, `sorcerer`, `warlock`, `wizard`

## Spellcasting Ability by Class

- **Bard**: Charisma
- **Cleric**: Wisdom
- **Druid**: Wisdom
- **Paladin**: Charisma
- **Ranger**: Wisdom
- **Sorcerer**: Charisma
- **Warlock**: Charisma
- **Wizard**: Intelligence

Used for:
- Spell attack bonus
- Spell save DC
- Number of spells prepared (for prepared casters)

## API Endpoints Reference

**Spells**:
- List all: `GET /api/2014/spells`
- Filter by level: `GET /api/2014/spells?level=1`
- Details: `GET /api/2014/spells/{index}`

**Class Spells**:
- Class spell list: `GET /api/2014/classes/{class}/spells`

**Schools**:
- List: `GET /api/2014/magic-schools`
- Details: `GET /api/2014/magic-schools/{index}`

## Tips

- **Always query spell details**: Don't guess effects, damage, or range
- **Track slots carefully**: Spellcasters run out fast, make it matter
- **Enforce concentration**: Only one concentration spell at a time
- **Narrate magic vividly**: Make spellcasting feel epic and powerful
- **Allow creativity**: Spells can be used in creative ways beyond combat
- **Remind about rituals**: Players often forget they can cast rituals for free

## Common Mistakes to Avoid

- **Don't forget to deduct spell slots**: Always update character file immediately
- **Don't skip concentration checks**: Caster takes damage = roll CON save
- **Don't allow multiple concentration spells**: It's one at a time, no exceptions
- **Don't forget components**: M components with costs must be consumed
- **Don't guess spell damage**: Always query API for dice and scaling
- **Don't forget range limits**: Touch spells need contact, ranged spells have max distance

## Integration with Other Skills

- **Combat** → Spell attacks, saving throws, concentration checks
- **Character Creation** → Starting spell selection
- **Character Advancement** → Learning new spells on level-up
- **Exploration** → Ritual casting *Detect Magic*, *Find Familiar*, etc.
- **Worldbuilding** → Magic items, spell scrolls, magical effects
