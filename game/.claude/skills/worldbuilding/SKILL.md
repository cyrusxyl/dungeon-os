---
name: Worldbuilding & Procedural Generation
description: Generate NPCs, locations, loot, equipment, and quest content on-the-fly for D&D campaigns. Use when the DM needs to create new content during play, improvise encounters, populate towns, generate treasure, manage merchant shops, look up equipment stats, or expand the world dynamically.
---

# Worldbuilding & Procedural Generation

Create engaging content procedurally: NPCs with personality, locations with atmosphere, loot with purpose, and quests with hooks.

## Campaign Story Bible

When starting a **new campaign** (no `dm_story.md` exists in the campaign folder), create one before play begins. Also create `{campaign}/canon.json` alongside it with `uv run dnd-cli canon init {campaign}` — do not create it by hand, so it starts schema-valid. `dm_story.md` is the narrative spine — the story you intend to tell. `canon.json` is the mechanical record the `dm-canon-procedures` skill reads and writes during play — the facts that have actually happened. Both files keep the story from drifting into incoherence across sessions.

Once `dm_story.md` names the campaign's villains and their quests (item 6, below), enter them into `canon.json` the same way — do not write the villain/clock JSON by hand:
```bash
uv run dnd-cli canon add-villain "{name}" "{goal}" "{trait}" --escape-plan "{how they escape capture}"
uv run dnd-cli canon add-clock "{villain name}" "{clock name}" {4|6|8} --description "{what it tracks}"
```
`add-clock` refuses any segment count other than 4, 6, or 8 (Operating Guide 2.2) — the command enforces this, so there is no need to double check it yourself.

### What to write

Save to `{campaign}/dm_story.md` with these sections:

1. **Core Premise** — One paragraph. The central conflict, the theme, what kind of story this is. Include one hook that pulls the players into the story at session 1.

2. **World Truths** — 3 to 5 facts that are always true in this world (example: "magic is rare"). Do not write the world's full history — write only what session 1 needs.

3. **The Full Conspiracy / Truth** — Everything that is *actually* happening behind the scenes, regardless of what the players know. Include names, motives, relationships, and hidden facts. Be specific.

4. **Story Branches** — 3-4 major directions the player could take. For each branch:
   - What triggers it
   - Key NPCs unlocked
   - How it escalates
   - What the endpoint looks like if they follow it through

5. **Pacing & Pressure Timers** — A table of world events that happen *on their own* if the players don't act. This makes the world feel alive. Format:
   ```
   | Event | Trigger | Sessions Until |
   ```
   Each row that belongs to a villain also becomes a clock in `canon.json` Part A. A clock has 4, 6, or 8 segments — pick the size closest to "Sessions Until" (a 1-3 session timer is a 4-segment clock; a longer or vaguer timer is 6 or 8). This table stays in `dm_story.md` as the human-readable version; the clock in `canon.json` is the one the `dm-canon-procedures` skill actually advances session to session.

6. **Key NPC Profiles** — Full profiles for any NPC who drives the plot. Include:
   - Actual goals (not just the face they show players)
   - Weakness or pressure point
   - What happens if they're killed, captured, or befriended

   For each of the campaign's 1-3 main villains, also give:
   - **One clear trait** the players will remember them by
   - **A way to escape capture** — do not let the players kill a main villain in an early encounter
   - **Three quests toward their goal** — these become the villain's clocks in `canon.json` Part A

7. **Player-Specific Hooks** — At least one hook per PC that ties their background/race/class into the main story.

8. **World State Tracking** — A table of variables the DM tracks silently (who knows what, who's alerted, what's been discovered).

### Rules for maintaining the bible

- **Update after each session**: Add new entries under "World State Tracking" when key facts change.
- **Never contradict it silently**: If a player action should change a major plot element, update the file to reflect the new reality.
- **Never show it to players**: Reference it for your own decisions only. The file header should note `<!-- DM EYES ONLY -->`.
- **Don't let players derail without consequence**: The Pressure Timers section ensures the world moves even if players ignore the main thread.
- **`dm_story.md` is intent, `canon.json` is record**: this file describes the story you plan to tell. `canon.json` is the file that governs what the AI DM must actually treat as true, per "Canon File & Anti-Drift Rules" in `AGENTS.md`. Session-to-session upkeep of `canon.json` (clock advances, thread staleness, session-end records) is the `dm-canon-procedures` skill's job, not this one's.

## NPC Generation

When players meet a new NPC (innkeeper, shopkeeper, guard, quest-giver):

### Quick NPC (Minor Character)

For background NPCs who don't need full stats:

1. **Generate basics**:
   - Name: Use fantasy name generator patterns or simple combinations
     - Human: "Gareth Cole", "Elena Voss", "Marcus Thorn"
     - Elf: "Silvanus Moonwhisper", "Alatari"
     - Dwarf: "Borin Ironforge", "Thura Stonefist"
   - Role/Occupation: Innkeeper, blacksmith, guard, merchant
   - One personality trait: Gruff, cheerful, suspicious, greedy, kind

2. **Add depth** (pick 1-2):
   - **Quirk**: Missing tooth, always humming, smells like garlic, nervous laugh
   - **Motivation**: Save for daughter's wedding, prove worth to guild, hide a past crime
   - **Secret**: Actually a retired adventurer, in debt to thieves' guild, knows about the treasure

3. **Save to file**:
   ```bash
   # Create NPC file at {campaign}/world/npcs/{name}.json
   ```

   Minimal format:
   ```json
   {
     "name": "Gareth the Innkeeper",
     "type": "humanoid",
     "personality": "Gruff but fair, suspicious of outsiders",
     "motivation": "Keep his inn profitable and avoid trouble",
     "secret": "His daughter is secretly dating a member of the Redbrands",
     "location": "Phandalin - Stonehill Inn",
     "relationship_to_party": "neutral"
   }
   ```

### Combat NPC (Has Stats)

For NPCs who might fight:

1. **Fetch monster stats** if using standard creature:
   ```bash
   uv run dnd-cli get monsters/{creature} --fields name,type,hit_points,armor_class,challenge_rating,strength,dexterity,constitution,intelligence,wisdom,charisma,actions
   ```

2. **Customize**: Add personality, motivation, secret

3. **Save** to `{campaign}/world/npcs/{name}.json` using full NPC schema, with `hp: {current, max}`, `armor_class`, `ability_scores` and `actions` (`attack_bonus`, `damage`): then `uv run dnd-cli encounter start <npc-id>` uses those stats and writes its HP back after the fight. A plain monster needs no file: `encounter start bandit:2`.

### NPC Interaction Memory

After meaningful interactions:

1. **Update NPC file** with `notes` field:
   ```json
   "notes": "Session 1: Party helped rescue from goblins, now friendly. Offered free rooms."
   ```

2. **Update relationship**:
   ```json
   "relationship_to_party": "friendly"
   ```

## Location Generation

When players enter a new area:

### Room/Area Description

Create vivid, immersive descriptions:

1. **Template structure**:
   - **Senses**: What do they see, hear, smell?
   - **Details**: Specific objects, features
   - **Atmosphere**: Mood, tension, comfort
   - **Hooks**: Interesting elements to investigate

2. **Example**:
   > "You push open the heavy oak door. The room beyond is dimly lit by flickering torches, their smoke curling up to a vaulted stone ceiling. The air smells of damp earth and old leather. Against the far wall, a desk sits buried under scrolls and maps. To your left, a locked iron chest catches the torchlight."

3. **Save to file** (optional for important locations):
   ```bash
   # Create location file at {campaign}/world/locations/{name}.md
   ```

   Format:
   ```markdown
   # The Dusty Archive

   A dimly lit chamber with vaulted ceilings and flickering torches...

   ## Exits
   - North: Hallway to main keep
   - East: Secret door (DC 15 Investigation) to treasure room

   ## Notable Features
   - Desk covered in ancient maps
   - Locked iron chest (DC 12 Thieves' Tools to open)
   - Fireplace with loose stone (hidden compartment)

   ## Hidden Elements
   - Trap: Poisoned needle in chest lock (DC 13 Perception, 1d4 poison damage, DC 11 CON save)
   - Secret: Map showing location of Wave Echo Cave
   ```

### Dungeon Room

For dungeon exploration:

1. **Purpose**: What was this room for? (Barracks, temple, prison, treasury)
2. **Current state**: Abandoned, monster lair, trapped, looted
3. **Contents**: Furniture, debris, creatures, treasure
4. **Dangers**: Traps (use schemas), environmental hazards
5. **Exits**: Where do doors/passages lead?

## Loot Generation

When players search bodies, chests, or complete encounters:

### By Challenge Rating

Use CR to determine appropriate loot:

**CR 0-4 (Weak enemies)**:
- Coins: 1d20 cp, 1d10 sp, 1d6 gp
- Items: Common gear (rope, torches, rations)
- Maybe: 1 minor healing potion (10% chance)

**CR 5-10 (Medium enemies)**:
- Coins: 2d20 gp, 1d100 sp
- Items: Quality weapons/armor, tools
- Maybe: Uncommon magic item (15% chance) - Bag of Holding, +1 Weapon

**CR 11-16 (Strong enemies)**:
- Coins: 5d100 gp, 2d100 pp
- Items: Fine equipment, gems (50-100 gp each)
- Likely: Uncommon or rare magic item (50% chance)

**CR 17+ (Legendary enemies)**:
- Coins: Hoards of gold, gems, art objects
- Items: Rare or very rare magic items
- Special: Unique legendary items with backstory

### Magic Items

Query API for item details:
```bash
uv run dnd-cli get magic-items/{item-name}
```

Or create custom items:
- **Name**: Descriptive and evocative
- **Effect**: What does it do mechanically?
- **Lore**: Who made it? What's its history?

Example: "**Dawnbringer** - Longsword, +2 to hit and damage, sheds bright light 15ft, extra 1d8 radiant vs undead"

### Adding Loot to Inventory

The players say who takes what; then one command per item:

```bash
uv run dnd-cli character item sireth add "Potion of Healing" --qty 2 --canon   # --canon also records it in canon (Part E)
uv run dnd-cli character gold sireth +15
```

Describe a magic item's effect in the story; record its powers with `canon add-fact` if they are canon-level.

## Equipment & Inventory Management

Handle equipment lookups, merchant shops, and inventory updates with API-sourced item stats.

### Equipment Lookup

When players want to know about a weapon, armor, or gear:

1. **Query equipment details**:
   ```bash
   # Full equipment data (cached)
   uv run dnd-cli get equipment/{equipment-index}

   # Or extract specific fields
   uv run dnd-cli get equipment/{equipment-index} --fields name,equipment_category,cost,weight,desc

   # Search for equipment
   uv run dnd-cli search equipment --category weapon --name sword
   ```

2. **For weapons**, get additional stats:
   ```bash
   uv run dnd-cli get equipment/{weapon-index} --fields name,cost,damage,range,properties,weapon_category,weapon_range
   ```

3. **For armor**, get AC details:
   ```bash
   uv run dnd-cli get equipment/{armor-index} --fields name,cost,armor_category,armor_class,str_minimum,stealth_disadvantage
   ```

4. **Query weapon properties** for clarification:
   ```bash
   # Quick reference
   uv run dnd-cli info weapon-properties {property-index}

   # Or only the fields you need
   uv run dnd-cli get weapon-properties/{property-index} --fields name,desc
   ```

   Common properties: `finesse`, `versatile`, `light`, `heavy`, `reach`, `thrown`, `two-handed`, `ammunition`, `loading`

### Merchant Shop Generation

When players visit a shop:

1. **Determine shop type**: Weaponsmith, armorer, general store, alchemist, magic shop

2. **Browse equipment by category**:
   ```bash
   # Get equipment category list (cached)
   uv run dnd-cli get equipment-categories/{category-index} --fields equipment

   # Or search by category
   uv run dnd-cli search equipment --category weapon
   ```

   Categories: `weapon`, `armor`, `adventuring-gear`, `tools`, `mounts-and-vehicles`, `ammunition`

3. **Generate stock**:
   - Small village shop: Common items, 1d6+2 types, 20% markup
   - Town shop: Common + uncommon items, 2d6+4 types, 10% markup
   - City shop: Full selection, base prices
   - Black market: Rare items, 50-200% markup

4. **Pricing**:
   - Use `cost.quantity` and `cost.unit` from API (gp, sp, cp)
   - Apply markup/discount as appropriate
   - Standard exchange: 1 gp = 10 sp = 100 cp

5. **Example merchant interaction**:
   ```
   DM: "Hargus the blacksmith shows you his wares. What are you looking for?"
   Player: "Do you have any rapiers?"
   DM: [Query API] "Aye, I've got a fine rapier here. 25 gold pieces. Light, nimble blade—perfect for a dextrous fighter."
   ```

### Equipment Purchase

```bash
uv run dnd-cli character gold sireth -25          # refuses if the character cannot pay
uv run dnd-cli character equip sireth rapier       # weapon: attack and damage worked out; armor or shield: AC worked out
uv run dnd-cli character item sireth add "Rope, hempen (50 feet)"     # gear that is not a weapon or armor
```

Price: the API `cost` with your markup (1 gp = 10 sp = 100 cp). `equip` adds the item to the inventory too. A character not proficient with a weapon: `equip ... --not-proficient`.

### Equipment Proficiency Validation

Before allowing equipment use:

1. **Check character proficiencies**:
   - Read character file for `proficiencies` or class-granted proficiencies
   - Common proficiencies from character creation skill

2. **Weapon proficiency**:
   - Simple weapons: Club, dagger, quarterstaff, light crossbow, etc.
   - Martial weapons: Longsword, rapier, longbow, greatsword, etc.
   - If not proficient: No proficiency bonus to attack rolls

3. **Armor proficiency**:
   - Light armor: Leather, studded leather
   - Medium armor: Hide, chain shirt, scale mail
   - Heavy armor: Chain mail, plate
   - If not proficient: Disadvantage on ability checks, saving throws, attack rolls using STR or DEX

4. **Query proficiency details** if needed:
   ```bash
   uv run dnd-cli get proficiencies/{proficiency-index} --fields name,type,classes,races
   ```

### Merchant Inventory Templates

**Weaponsmith**:
- Martial weapons: Longsword, greatsword, battleaxe, warhammer, longbow
- Simple weapons: Handaxe, spear, light crossbow
- Ammunition: Arrows (20), bolts (20)
- Maybe: +1 weapon (rare, expensive)

**Armorer**:
- Light armor: Leather, studded leather
- Medium armor: Hide, chain shirt, scale mail, half plate
- Heavy armor: Chain mail, splint, plate
- Shields: Wooden, steel

**General Store**:
- Adventuring gear: Rope, torches, rations, waterskin, backpack, bedroll
- Tools: Thieves' tools, tinker's tools, healer's kit
- Miscellaneous: Lantern, oil, chalk, crowbar, hammer

**Alchemist**:
- Potions: Healing (2d4+2), greater healing (4d4+4), antitoxin
- Supplies: Alchemist's supplies, herbalism kit, healer's kit
- Rare: Potion of invisibility, potion of climbing

### Loot Distribution with Equipment

Name the items with their API stats, let the players divide them, then `character item ... add` (and `character equip` for gear they use at once).

### Equipment Maintenance

Track equipment condition (optional rule):

- **Damaged**: After critical fail in combat, roll for weapon/armor damage
- **Repair**: Costs 10% of item value, requires smith or appropriate tools
- **Broken**: Unusable until repaired

## Quest Generation

When players need a quest hook:

### Quest Template

1. **Hook**: Why should players care?
   - "The mayor's daughter is missing"
   - "Strange noises from the old mill at night"
   - "Merchant offers 100gp to escort caravan"

2. **Goal**: What's the objective?
   - Rescue, retrieve, defeat, investigate, escort, negotiate

3. **Obstacles**: What's in the way?
   - Monsters, rival adventurers, environmental hazards, time pressure

4. **Reward**: What do they get?
   - Gold, magic items, reputation, information, allies

5. **Twist** (optional): Complication midway
   - "The daughter was kidnapped by her secret boyfriend"
   - "The monsters are protecting something valuable"

### Save Quest

Create quest file at `{campaign}/world/quests/{quest-id}.json`:

```json
{
  "id": "rescue-sildar",
  "title": "Rescue Sildar Hallwinter",
  "description": "Gundren's bodyguard was captured by goblins and taken to Cragmaw Hideout",
  "status": "active",
  "objectives": [
    {"task": "Find Cragmaw Hideout", "completed": false},
    {"task": "Defeat or sneak past goblins", "completed": false},
    {"task": "Free Sildar from captivity", "completed": false}
  ],
  "reward": "Sildar's gratitude, 50gp, information about Wave Echo Cave",
  "notes": "Sildar knows about the Black Spider and can provide quest lead"
}
```

Update `state.json` quest_log:
```json
"quest_log": [
  {
    "id": "rescue-sildar",
    "title": "Rescue Sildar Hallwinter",
    "status": "active",
    "progress": "Found goblin trail leading east"
  }
]
```

## Random Tables

Use roll-cli for random selection:

### Random Encounter (Wilderness)

```bash
uv run roll 1d12 -v
```

1-3: No encounter
4-6: Hostile (bandits, wolves, goblins)
7-9: Neutral (travelers, merchants, animals)
10-11: Helpful (friendly NPC, safe campsite, healing herbs)
12: Special (mysterious stranger, magic item, plot hook)

### NPC Personality

Roll 1d20 for personality trait:
1. Greedy
2. Cowardly
3. Brave
4. Curious
5. Suspicious
6. Friendly
7. Gruff
8. Cheerful
9. Scholarly
10. Superstitious
11. Drunk
12. Secretive
13. Boastful
14. Humble
15. Aggressive
16. Protective
17. Cynical
18. Optimistic
19. Mysterious
20. Eccentric

### Treasure Type

Roll 1d6:
1-3: Coins only
4-5: Coins + mundane items
6: Coins + magic item

## Best Practices

- **Consistency**: Name NPCs immediately and write them down—don't rename them later
- **Reuse**: If players return to the inn, the same innkeeper should be there
- **Connections**: Link new content to existing story (NPC knows about main quest)
- **Proportionality**: Don't generate a full stat block for a background villager
- **Player-driven**: Generate content based on what players investigate/ask about
- **Record everything**: Save generated content to files immediately

## Integration with Other Skills

- **After combat** → Generate loot from defeated enemies
- **Social encounters** → Generate NPCs on-the-fly when players ask questions
- **Exploration** → Generate room descriptions as players explore
- **Quest completion** → Update quest status in files and state.json
