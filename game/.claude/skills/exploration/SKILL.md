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

### Step 2: Set the DC

| DC | Difficulty | Example |
|---|---|---|
| 5 | Very easy | climb a knotted rope |
| 10 | Easy | climb a rough wall, hide in thick forest |
| 15 | Medium | climb a sheer wall, pick a simple lock |
| 20 | Hard | climb a slippery surface, pick a complex lock |
| 25 | Very hard | climb an overhang, forge a royal seal |
| 30 | Nearly impossible | climb a perfectly smooth wall |

Contested check: roll both sides (Stealth vs Perception) and compare.

### Step 3: Roll with one command

```bash
uv run dnd-cli check sireth stealth --dc 15
uv run dnd-cli check sireth perception --dc 14 --adv          # Help, or a good position: --adv; poor light: --dis
uv run dnd-cli check sireth con --dc 12                       # a raw ability check
uv run dnd-cli check all stealth --dc 13                      # group check: half or more must succeed
uv run dnd-cli check all perception --passive                 # passive scores, no roll
uv run dnd-cli check goblin#1 stealth --secret                # a creature in the encounter; hidden from the stage
```

On the visual stage, a player character rolls their own check with `@roll` (the `stage` skill, rule 4). The commands read each character's bonus from the sheet (proficiency and expertise are already in it), rolls, compares with the DC, and shows the dice on the stage. Do not work out modifiers yourself. A natural 20 or 1 on a check is not an automatic success or failure, but make the outcome memorable.

### Step 4: Narrate

- "Your fingers find the pins (**18 vs DC 15**). The lock clicks open."
- "You fumble the picks (**12 vs DC 15**). The lock holds."

## Passive Checks

Passive score = 10 + the skill bonus (+5 with advantage, -5 with disadvantage): `uv run dnd-cli check all perception --passive`. Use it to notice hidden enemies, traps and ambushes without a roll (Perception), small details (Investigation), and lies or tension (Insight). A trap with DC 15 is noticed by a passive Perception of 15 or more.

## Ability Checks (Raw Ability)

When no skill applies, check the ability itself (`check <who> str`): STR for brute force, DEX for quick reflexes, CON to hold your breath or resist poison, INT for logic and memory, WIS for a gut feeling, CHA for force of personality.

## Group Checks

When the whole party tries the same task (sneaking past guards, swimming a river), `uv run dnd-cli check all <skill> --dc N`: the group succeeds when half or more succeed.

Helping: one character helps another, who then rolls with `--adv`.

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
uv run dnd-cli get proficiencies/thieves-tools --fields name,desc,classes
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
uv run dnd-cli get proficiencies/{tool-index}
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
