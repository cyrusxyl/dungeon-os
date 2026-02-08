---
name: Combat Resolution
description: Handle D&D 5e combat encounters including initiative, attacks, damage, HP tracking, conditions, status effects, and turn coordination. Use when combat starts, players attack, enemies engage, spells apply conditions, or initiative is rolled. Supports multi-player coordination and condition enforcement.
---

# Combat Resolution

Handle all aspects of D&D 5e combat: initiative, attacks, damage, HP tracking, and turn order.

## Pre-Combat Setup

When combat begins:

1. **Identify participants**:
   - Read player characters from `{campaign}/characters/*.json`
   - For monsters/NPCs, either load from `{campaign}/world/npcs/{name}.json` or fetch from API:
     ```bash
     curl -sL "https://www.dnd5eapi.co/api/2014/monsters/{monster-name}" | jq '{
       name: .name,
       hp: .hit_points,
       ac: .armor_class[0].value,
       dex_mod: ((.dexterity - 10) / 2 | floor),
       actions: .actions
     }'
     ```
   - Save fetched monsters to `{campaign}/world/npcs/{name}-{number}.json` for this encounter

2. **Create combat state**:
   - Update `state.json` with `active_encounter` object
   - Initialize participants list

## Initiative Phase

Roll initiative for all combatants:

```bash
source .venv/bin/activate && roll 1d20+{dex_modifier} -v
```

The `-v` flag shows breakdown: `Rolled: 1d20: [15] Adding: 15 + 3 = 18`

1. Roll for each PC (use their dexterity modifier from character sheet)
2. Roll for each NPC/monster (use their dexterity modifier)
3. Sort results highest to lowest
4. Update `state.json`:
   ```json
   "active_encounter": {
     "type": "combat",
     "participants": ["aragorn", "legolas", "goblin-1", "goblin-2"],
     "initiative_order": [
       {"name": "legolas", "initiative": 18},
       {"name": "goblin-1", "initiative": 16},
       {"name": "aragorn", "initiative": 14},
       {"name": "goblin-2", "initiative": 12}
     ],
     "current_turn": "legolas"
   }
   ```
5. Narrate combat start with dramatic description

## Turn Execution

For each turn in initiative order:

### 1. Announce Turn

Check `current_turn` in `state.json`:
- If PC: Identify controlling player from `{campaign}/players/{id}.json`
- Announce: "**{Character}'s turn!** ({Player}, what do you do?)"
- If NPC: Determine action based on tactics

### 2. Resolve Actions

#### Attack Action

Player declares: "I attack the goblin with my longsword"

**Step 1: Get attacker's stats**
- Read `{campaign}/characters/{name}.json`
- Find weapon: `weapons[].attack_bonus` and `weapons[].damage`
- Or calculate: attack_bonus = proficiency_bonus + STR_modifier (or DEX for finesse)

**Step 2: Get target's AC**
- Read target's file for `armor_class`

**Step 3: Roll to hit**
```bash
source .venv/bin/activate && roll 1d20+{attack_bonus} -v
```

**Step 4: Compare to AC**
- If roll ≥ AC: Hit! Roll damage
- If roll < AC: Miss, narrate

**Step 5: Roll damage (on hit)**
```bash
source .venv/bin/activate && roll {damage_dice}+{modifier} -v
```
Example: `roll 1d8+3 -v` for longsword with +3 STR

**Step 6: Update target HP**
- Read target's current HP
- Subtract damage
- Write new HP to target's file using Edit tool
- If HP ≤ 0: Creature is down/dead

**Step 7: Narrate**
- Hit: "Your blade flashes (**rolled 18 vs AC 15**). Steel bites deep—**7 damage**—and the goblin staggers."
- Miss: "Your swing goes wide (**rolled 12 vs AC 15**) as the goblin ducks."

#### Spell Attack

Player declares: "I cast Fire Bolt at the goblin"

**Step 1: Query spell**
```bash
curl -sL "https://www.dnd5eapi.co/api/2014/spells/{spell-name}" | jq '{
  name: .name,
  level: .level,
  damage: .damage,
  attack_type: .attack_type,
  dc: .dc
}'
```

**Step 2: Check spell slots** (if spell level > 0)
- Read `{campaign}/characters/{name}.json`
- Check `spellcasting.spell_slots["{level}"].remaining`
- If 0: "You're out of {level}-level spell slots!"

**Step 3: Resolve attack**
- If `attack_type: "RANGED"`: Roll spell attack (1d20 + spell_attack_bonus)
- If has save DC: Target rolls save (see Saving Throws below)

**Step 4: Roll damage**
- Parse damage from API (e.g., "8d6")
- Roll: `source .venv/bin/activate && roll 8d6 -v`

**Step 5: Update**
- Deduct spell slot: Edit character file, decrement `spell_slots["{level}"].remaining`
- Apply damage to target

#### Skill Check in Combat

Example: "I want to shove the goblin off the ledge"

**Step 1: Determine skill**
- Shove = Athletics (STR)
- Grapple = Athletics (STR)
- Hide = Stealth (DEX)

**Step 2: Get modifier**
- Read character's `skills.{skill_name}` or ability modifier

**Step 3: Set DC**
- Contest: Opponent rolls opposing check
- Standard: DM sets DC (10=easy, 15=medium, 20=hard)

**Step 4: Roll**
```bash
source .venv/bin/activate && roll 1d20+{modifier} -v
```

**Step 5: Narrate result**

### 3. Update State

After each turn:
- Update `state.json`: set `current_turn` to next in initiative order
- Update any changed HP/status in character/NPC files
- Narrate the result vividly

### 4. Move to Next Turn

Cycle through `initiative_order`, loop back to top when reaching end.

## Conditions & Status Effects

Track and enforce D&D 5e conditions with mechanical effects.

### Applying Conditions

When a spell, ability, or effect applies a condition:

1. **Query condition details**:
   ```bash
   curl -sL "https://www.dnd5eapi.co/api/2014/conditions/{condition-index}" | jq '{
     name: .name,
     desc: .desc
   }'
   ```

   Common conditions: `blinded`, `charmed`, `deafened`, `frightened`, `grappled`, `incapacitated`, `invisible`, `paralyzed`, `petrified`, `poisoned`, `prone`, `restrained`, `stunned`, `unconscious`, `exhaustion`

2. **Update combat state**:
   ```json
   "active_encounter": {
     "conditions": {
       "goblin-1": [
         {
           "condition": "poisoned",
           "duration": "1 minute",
           "source": "Ray of Sickness",
           "save_dc": 13,
           "save_type": "CON"
         }
       ],
       "aragorn": [
         {
           "condition": "prone",
           "duration": "until stands up",
           "source": "knocked down"
         }
       ]
     }
   }
   ```

3. **Narrate application**:
   - "The goblin reels back, green-faced and retching (**Poisoned**)."
   - "Aragorn hits the ground hard (**Prone**)."

### Condition Effects

Enforce these mechanical effects automatically:

**Blinded**:
- Attack rolls have disadvantage
- Attacks against have advantage
- Auto-fail ability checks requiring sight

**Charmed**:
- Can't attack charmer or target with harmful effects
- Charmer has advantage on social checks

**Frightened**:
- Disadvantage on ability checks and attack rolls while source is in sight
- Can't willingly move closer to source

**Grappled**:
- Speed becomes 0
- Can't benefit from bonuses to speed

**Incapacitated**:
- Can't take actions or reactions

**Invisible**:
- Can't be seen without special sense
- Attack rolls have advantage
- Attacks against have disadvantage

**Paralyzed**:
- Incapacitated (can't take actions/reactions)
- Auto-fail STR and DEX saves
- Attacks against have advantage
- Melee attacks within 5 ft are critical hits

**Poisoned**:
- Disadvantage on attack rolls
- Disadvantage on ability checks

**Prone**:
- Disadvantage on attack rolls
- Melee attacks against have advantage
- Ranged attacks against have disadvantage
- Costs half movement to stand up

**Restrained**:
- Speed becomes 0
- Attack rolls have disadvantage
- Attacks against have advantage
- Disadvantage on DEX saves

**Stunned**:
- Incapacitated (can't take actions/reactions)
- Auto-fail STR and DEX saves
- Attacks against have advantage

**Unconscious**:
- Incapacitated, can't move or speak
- Drops what it's holding, falls prone
- Auto-fail STR and DEX saves
- Attacks against have advantage
- Melee attacks within 5 ft are critical hits

**Exhaustion** (levels 1-6):
1. Disadvantage on ability checks
2. Speed halved
3. Disadvantage on attack rolls and saves
4. HP maximum halved
5. Speed reduced to 0
6. Death

### Enforcing Conditions During Combat

**Before attack roll**:
- Check if attacker has conditions: Apply disadvantage for `blinded`, `frightened`, `poisoned`, `prone`, `restrained`
- Check if target has conditions: Apply advantage for attacks against `blinded`, `paralyzed`, `prone` (melee only), `restrained`, `stunned`, `unconscious`

**Before saving throw**:
- Check conditions: `Paralyzed` or `stunned` = auto-fail STR/DEX saves
- Apply disadvantage/advantage as appropriate

**During movement**:
- Check conditions: `Grappled`, `restrained`, `prone` (costs half movement), `exhaustion` level 2+ (halved speed), level 5 (speed 0)

**Start of turn**:
- Check condition duration: "Until end of turn", "1 minute", "concentration", etc.
- Prompt saves if allowed: "The goblin can make a CON save (DC 13) to end Poisoned."

### Condition Duration Tracking

**Instantaneous**: Apply once, no tracking
**Until end of turn**: Remove at end of creature's turn
**1 minute (10 rounds)**: Decrement round counter, remove at 0
**Concentration**: Tied to caster's concentration, remove if caster loses concentration
**Until condition met**: Remove when specified action occurs (e.g., "until stands up")

Example tracking:
```json
{
  "condition": "hold-person",
  "duration": "concentration, 1 minute",
  "rounds_remaining": 10,
  "source": "Wizard's spell",
  "save_dc": 14,
  "save_type": "WIS",
  "save_on_turn_end": true
}
```

### Removing Conditions

**Automatically**:
- Duration expires
- Condition's trigger met (stands up from prone)
- Source removed (charmer dies)

**By action**:
- Lesser Restoration spell removes many conditions
- Medicine check to stabilize unconscious

**By save**:
- Some conditions allow saves at end of turn
- Roll save, compare to DC, remove on success

**Update state**:
```bash
# Remove condition from active_encounter.conditions
```

### Concentration Checks

When a concentrating caster takes damage:

1. **Determine DC**: DC = 10 or half damage taken, whichever is higher
2. **Roll CON save**:
   ```bash
   source .venv/bin/activate && roll 1d20+{con_modifier} -v
   ```
3. **On failure**: Concentration breaks, remove all concentration-based conditions/spells

### Damage Types

Query damage type information:

```bash
curl -sL "https://www.dnd5eapi.co/api/2014/damage-types/{damage-type}" | jq '{
  name: .name,
  desc: .desc
}'
```

Common types: `acid`, `bludgeoning`, `cold`, `fire`, `force`, `lightning`, `necrotic`, `piercing`, `poison`, `psychic`, `radiant`, `slashing`, `thunder`

**Resistances**: Take half damage
**Vulnerabilities**: Take double damage
**Immunities**: Take no damage

Check creature stat blocks for resistances/immunities and apply when calculating damage.

## Saving Throws

When a spell or effect requires a save:

**Step 1: Determine save type**
- From spell API: `dc.dc_type.name` (e.g., "DEX", "WIS")

**Step 2: Get target's modifier**
- Read target file for ability modifier

**Step 3: Get save DC**
- For spells: caster's `spell_save_dc` from their character sheet
- For monster abilities: from monster stat block

**Step 4: Roll save**
```bash
source .venv/bin/activate && roll 1d20+{modifier} -v
```

**Step 5: Compare**
- Success: Usually half damage or no effect
- Failure: Full damage or full effect

## Combat End

When all enemies are defeated or players flee:

1. **Update state**:
   ```json
   "active_encounter": null,
   "party_status": "Exploring"
   ```

2. **Award XP** (if using XP system):
   - Read monster CR, calculate XP
   - Add to each PC's `experience_points`

3. **Loot & Rest**:
   - Prompt players: "The battle is won. Search the bodies? Take a short rest?"
   - Generate loot if appropriate (use worldbuilding skill)

## Multi-Player Coordination

- **Verify player control**: Before allowing actions, check `{campaign}/players/{id}.json` to confirm player controls the character
- **No editing other characters**: Players can only modify their own characters' HP, inventory, etc.
- **Turn announcements**: Clearly state whose turn it is and which player controls them
- **Simultaneous actions**: If multiple players want to act out-of-turn (readied actions, reactions), handle in initiative order with DM judgment

## Tips

- **Narrate first, mechanics second**: "Your arrow flies true" before "rolled 18 vs AC 15"
- **Keep combat moving**: Don't wait too long for player input, prompt them
- **Track status effects**: Note conditions (prone, grappled, etc.) in encounter state
- **Critical hits (natural 20)**: Double damage dice (not modifiers)
- **Critical fails (natural 1)**: Automatic miss, narrate dramatically
- **Death saves**: When PC reaches 0 HP, track death saves in character file

## Common Mistakes to Avoid

- **Don't hallucinate AC or HP**: Always read from files
- **Don't forget to save changes**: Edit files immediately after HP changes
- **Don't skip spell slot checks**: Wizards can't cast infinite Fireballs
- **Don't mix up attack bonus and damage**: Attack determines if hit, damage determines how much hurt
