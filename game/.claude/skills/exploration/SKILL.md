---
name: Exploration & Skill Checks
description: Handle D&D 5e skill checks, ability checks, passive scores, and exploration mechanics. Use when players search for clues, pick locks, climb walls, track creatures, or attempt any skill-based action. Includes DC guidelines and group check resolution.
---

# Exploration & Skill Checks

Resolve skill checks, ability checks, and exploration activities with API-sourced skill descriptions and proper DC scaling.

## Skill Check Resolution

When a player attempts a skill-based action:

### Step 1: Identify Appropriate Skill

Match action to skill:

**Strength-based**:
- Athletics: Climb, jump, swim, grapple, shove, break objects

**Dexterity-based**:
- Acrobatics: Balance, tumble, escape grapples, aerial maneuvers
- Sleight of Hand: Pick pockets, conceal objects, perform tricks
- Stealth: Hide, move silently, tail someone

**Intelligence-based**:
- Arcana: Recall magic lore, identify spells, understand magical effects
- History: Recall historical events, legendary figures, ancient civilizations
- Investigation: Search for clues, deduce information, find hidden objects
- Nature: Recall nature lore, identify plants/animals, predict weather
- Religion: Recall religious lore, identify holy symbols, recognize deities

**Wisdom-based**:
- Animal Handling: Calm animals, train creatures, intuit animal behavior
- Insight: Detect lies, read body language, sense motivations
- Medicine: Stabilize dying, diagnose illness, treat wounds
- Perception: Notice details, spot hidden objects, hear sounds
- Survival: Track creatures, forage, navigate wilderness, predict weather

**Charisma-based**:
- Deception: Lie convincingly, disguise, create false impressions
- Intimidation: Threaten, coerce, frighten
- Performance: Sing, dance, act, entertain
- Persuasion: Convince, negotiate, inspire, make requests

### Step 2: Query Skill Details (if needed)

```bash
curl -sL "https://www.dnd5eapi.co/api/2014/skills/{skill-index}" | jq '{
  name: .name,
  desc: .desc,
  ability_score: .ability_score.name
}'
```

Use this to clarify what a skill covers or which ability score it uses.

### Step 3: Determine DC (Difficulty Class)

**Standard DCs**:
- **Very Easy (DC 5)**: Climbing a knotted rope, noticing something obvious
- **Easy (DC 10)**: Climbing a rough surface, hiding in thick forest
- **Medium (DC 15)**: Climbing a sheer wall, picking a simple lock
- **Hard (DC 20)**: Climbing a slippery surface, picking a complex lock
- **Very Hard (DC 25)**: Climbing an overhanging cliff, forging a royal seal
- **Nearly Impossible (DC 30)**: Climbing a perfectly smooth wall, convincing an enemy you're their ally

**Contested checks**: Opponent rolls opposing skill (e.g., Stealth vs Perception)

### Step 4: Get Character's Modifier

Read character file:

1. **Check if proficient**: Look for skill in `skills` object
2. **Get modifier**:
   - If proficient: `ability_modifier + proficiency_bonus`
   - If not proficient: `ability_modifier` only
   - If expertise: `ability_modifier + (proficiency_bonus × 2)`

### Step 5: Roll the Check

```bash
source .venv/bin/activate && roll 1d20+{modifier} -v
```

**Advantage/Disadvantage**:
- Advantage: Roll twice, take higher
  ```bash
  source .venv/bin/activate && roll 2d20kh1+{modifier} -v
  ```
- Disadvantage: Roll twice, take lower
  ```bash
  source .venv/bin/activate && roll 2d20kl1+{modifier} -v
  ```

### Step 6: Compare to DC

- **Success**: Result ≥ DC
- **Failure**: Result < DC
- **Critical success (natural 20)**: Automatic success, exceptional result
- **Critical failure (natural 1)**: Automatic failure, complications

### Step 7: Narrate Outcome

**Success**:
- "Your fingers find the pins in the lock (**rolled 18 vs DC 15**). With a satisfying *click*, it opens."

**Failure**:
- "You fumble with the lock picks (**rolled 12 vs DC 15**). The mechanism remains stubbornly locked."

**Critical success**:
- "Your pick slides home perfectly (**natural 20!**). The lock springs open instantly, and you notice a hidden compartment inside the chest."

**Critical failure**:
- "Your pick snaps off in the lock (**natural 1**). The lock is now jammed and requires a DC 20 STR check to force open."

## Passive Checks

For continuous awareness without active rolling:

### Passive Perception

**Calculate**: 10 + Perception modifier

**Use for**:
- Noticing hidden enemies
- Spotting traps without searching
- Hearing distant sounds
- Seeing ambushes

**Example**: Character with +5 Perception has Passive Perception 15.

If trap has DC 15 to notice, they automatically spot it. If DC 16, they don't unless actively searching.

### Passive Investigation

**Calculate**: 10 + Investigation modifier

**Use for**:
- Noticing small details
- Spotting inconsistencies
- Recalling information

### Passive Insight

**Calculate**: 10 + Insight modifier

**Use for**:
- Detecting lies automatically
- Sensing hidden motives
- Reading tension in a room

**Track passive scores**: Add to character file for quick reference.

## Ability Checks (Raw Ability)

When no specific skill applies:

**Strength checks**: Brute force without Athletics
**Dexterity checks**: Quick reflexes without Acrobatics/Sleight/Stealth
**Constitution checks**: Endurance, resist poison, hold breath
**Intelligence checks**: Logic, memory without specific skill
**Wisdom checks**: Intuition, awareness without specific skill
**Charisma checks**: Force of personality without specific skill

**Roll**: 1d20 + ability modifier (no proficiency bonus)

### Example Ability Checks

- **CON check**: Hold breath underwater (DC 10 + 1 per previous round)
- **STR check**: Break down a door (DC based on door strength)
- **WIS check**: Sense something is wrong (gut feeling)
- **CHA check**: Make a good impression (raw charisma)

## Group Checks

When entire party attempts same task:

### Standard Group Check

**Method**: Everyone rolls, majority succeeds = group succeeds

**Example**: Sneaking past guards
1. All characters roll Stealth
2. Count successes vs failures
3. If more succeed than fail: Group sneaks past
4. If more fail than succeed: Guards notice the group

**Use for**: Moving stealthily, swimming across river, climbing cliff

### Helping

**Rule**: One character can Help another, granting advantage

**Requirements**:
- Helper must be proficient in the skill OR
- DM judges helper can meaningfully assist

**Example**: "I help Rogue pick the lock" → Rogue rolls with advantage

## Exploration Activities

While exploring dungeons/wilderness:

### Searching a Room

**Action**: Investigation check
**DC**: Based on how well hidden

**Process**:
1. Player declares what they're searching (desk, floor, walls)
2. Set DC based on concealment
3. Roll Investigation
4. On success: "You notice a loose stone in the floor..."

### Tracking

**Action**: Survival check
**DC**: Based on terrain and age of tracks

**Modifiers**:
- Fresh tracks: DC 10
- Old tracks: DC 15-20
- Hard ground: +5 DC
- Soft ground: -5 DC
- Rain/snow: +5-10 DC

### Finding Food/Water

**Action**: Survival check
**DC**: Based on terrain

- Abundant (forest, coast): DC 10
- Moderate (plains, hills): DC 15
- Scarce (desert, mountains): DC 20

**Result**: Find enough food/water for 1d6 people per success

### Navigating Wilderness

**Action**: Survival check
**DC**: Based on terrain and conditions

- With map: DC 10
- Without map, landmarks visible: DC 15
- Without map, featureless terrain: DC 20
- Poor weather: +5 DC

**Result**: Success = travel without getting lost, Failure = party goes off-course

## Travel Pace

**Normal pace**: 24 miles/day, can use Stealth with -5 penalty
**Fast pace**: 30 miles/day, -5 to Passive Perception, can't use Stealth
**Slow pace**: 18 miles/day, +5 to Passive Perception, can use Stealth

## Common Exploration DCs

**Perception**:
- Notice ordinary details: DC 10
- Spot hidden door: DC 15
- Hear whispered conversation: DC 15
- Notice invisible creature: DC 20

**Investigation**:
- Search typical room: DC 10
- Find secret compartment: DC 15
- Decipher coded message: DC 15-20
- Find magically hidden object: DC 20+

**Stealth**:
- Hide in dim light: DC 10
- Hide in shadows: DC 15
- Hide in plain sight: DC 20
- Hide from creature with blindsight: DC 25

**Arcana**:
- Identify common spell: DC 10
- Identify rare spell: DC 15
- Understand magical device: DC 15-20
- Decipher ancient magical runes: DC 20-25

**Athletics**:
- Climb rough surface: DC 10
- Climb typical wall: DC 15
- Climb slippery surface: DC 20
- Swim in calm water: DC 10
- Swim in rough water: DC 15
- Swim in stormy sea: DC 20

**Sleight of Hand**:
- Plant an object on someone: DC 10
- Pick a simple lock: DC 15
- Pick a complex lock: DC 20
- Conceal small object: DC 15

## Tool Proficiencies

Some checks require tools:

### Thieves' Tools

Required for picking locks and disarming traps.

**Query proficiency**:
```bash
curl -sL "https://www.dnd5eapi.co/api/2014/proficiencies/thieves-tools" | jq '{
  name: .name,
  desc: .desc,
  classes: .classes
}'
```

**Check**: DEX (Sleight of Hand) + proficiency bonus (if proficient)

### Other Tools

- Alchemist's Supplies: Craft potions, identify substances
- Herbalism Kit: Gather herbs, create remedies
- Navigator's Tools: Navigate by stars, chart course
- Forgery Kit: Create fake documents
- Disguise Kit: Create disguises

**Query any tool**:
```bash
curl -sL "https://www.dnd5eapi.co/api/2014/proficiencies/{tool-index}" | jq
```

## API Endpoints Reference

**Skills**:
- List: `GET /api/2014/skills`
- Details: `GET /api/2014/skills/{index}`

**Ability Scores**:
- List: `GET /api/2014/ability-scores`
- Details: `GET /api/2014/ability-scores/{index}`

**Proficiencies**:
- List: `GET /api/2014/proficiencies`
- Details: `GET /api/2014/proficiencies/{index}`

## Tips

- **Ask for intent**: "What are you trying to accomplish?" before calling for a check
- **Don't over-roll**: Not every action needs a check
- **Failure isn't always nothing**: On failed check, give partial information or create complication
- **Let players describe**: After roll, ask "How do you do it?" for successes
- **Use passive scores**: Reduce die rolling for routine awareness
- **Reward creativity**: Lower DC or grant advantage for clever approaches

## Common Mistakes to Avoid

- **Don't call for impossible checks**: DC 30 climb isn't an invitation to try
- **Don't ignore passive scores**: They should catch obvious threats automatically
- **Don't forget advantage/disadvantage**: Environmental factors matter
- **Don't punish natural 1s too harshly**: Failure is enough, don't add humiliation
- **Don't allow retries without change**: If they failed, they can't try again without new approach

## Integration with Other Skills

- **Combat** → Initiative uses DEX (Acrobatics), Grapple uses STR (Athletics)
- **Worldbuilding** → Set DCs for traps, locks, hidden objects in generated rooms
- **Social** → Persuasion, Deception, Intimidation, Insight checks
- **Magic** → Arcana checks to identify spells, understand magic
