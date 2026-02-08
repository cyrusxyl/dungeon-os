# DungeonOS

**An Agentic Dungeon Master System for Multi-Player D&D 5e Campaigns**

DungeonOS transforms agentic coders (like Claude Code) into intelligent Dungeon Masters by leveraging their native strengths: file management, tool orchestration, and creative narrative generation—while offloading rules enforcement and randomness to external tools.

## Core Concept

Unlike traditional AI DMs that hallucinate rules and forget details, DungeonOS:
- ✅ **Stores world state in files** - HP, inventory, NPCs persist across sessions
- ✅ **Uses external tools** - API for rules, roll-cli for dice, no guessing
- ✅ **Loads skills progressively** - Combat skill only loads during combat
- ✅ **Supports multi-player** - Player permissions, turn coordination
- ✅ **Generates content procedurally** - NPCs, loot, locations on-the-fly

## Quick Start

### Prerequisites

1. **uv** (Python package manager): https://docs.astral.sh/uv/
2. **roll-cli** (dice roller):
   ```bash
   uv pip install roll-cli
   ```
3. **curl** and **jq** (usually pre-installed)

### Installation

1. Clone or extract DungeonOS to your machine
2. Verify tools work:
   ```bash
   # Test dice rolling (activate venv if needed)
   roll 1d20+5 -v

   # Test D&D API
   curl -sL "https://www.dnd5eapi.co/api/2014/spells/fireball" | jq .name
   ```

### Entering DM Mode

From your workspace:
```bash
cd dungeon-os/
```

When you `cd` into the `dungeon-os/` directory, the agentic coder switches from "coder mode" to "DM mode" by:
- Loading `AGENT.md` as system prompt
- Discovering skills in `./.claude/skills/`
- Reading `campaigns/active.json` to find the active campaign

### Starting Your First Session

1. **Load the example campaign:**
   The `campaigns/active.json` file already points to `example-campaign`.

2. **Greet the DM:**
   ```
   Hello! I'm ready to play.
   ```

3. **Identify yourself:**
   ```
   I'm Alice, playing Aragorn.
   ```

4. **Start playing:**
   ```
   What do we see in the town square?
   ```

The DM will:
- Read `state.json` to understand current situation
- Check `players/player1.json` to confirm you control Aragorn
- Load appropriate skills based on your actions
- Narrate vividly and track all changes in files

## How It Works

### File System = Game State

All campaign data lives in `/campaigns/{campaign-name}/`:

```
campaigns/example-campaign/
├── state.json              # Current game state (location, time, encounter)
├── config.json             # Campaign settings
├── session_log.md          # Narrative history
├── players/                # Player metadata
│   ├── player1.json        # Alice controls Aragorn
│   └── player2.json        # Bob controls Legolas
├── characters/             # Character sheets
│   ├── aragorn.json
│   └── legolas.json
└── world/                  # World content
    ├── npcs/               # NPCs and monsters
    ├── locations/          # Room descriptions
    └── quests/             # Quest tracking
```

### Skills = DM Knowledge

Skills in `./.claude/skills/` teach the DM how to handle specific situations:

- **`/combat`** - Initiative, attacks, damage, HP tracking
- **`/worldbuilding`** - Generate NPCs, loot, locations on-the-fly

Skills load only when needed, keeping context lean.

### Tools = Deterministic Rules

The DM uses external tools instead of guessing:

- **curl** → Query D&D 5e API for spell details, monster stats
- **roll-cli** → Roll dice with `roll 1d20+5 -v`
- **File edits** → Update HP, inventory immediately after changes

### Multi-Player Support

Each player has a metadata file:
```json
{
  "player_id": "player1",
  "player_name": "Alice",
  "characters_controlled": ["aragorn"],
  "permissions": {
    "can_edit_own_characters": true,
    "can_view_other_sheets": false
  }
}
```

The DM:
- Verifies player identity before actions
- Manages turn order in combat
- Prevents players from editing others' characters

## Example Gameplay

### Combat Encounter

**Player (Alice):** "I attack the goblin with my longsword!"

**DM:**
1. Loads `/combat` skill
2. Reads Aragorn's character sheet for attack bonus
3. Fetches goblin stats from API or existing file
4. Rolls: `roll 1d20+5 -v` → Result: 18
5. Compares 18 vs goblin AC 15 → Hit!
6. Rolls damage: `roll 1d8+3 -v` → Result: 7
7. Updates goblin HP in file: 11 → 4
8. **Narrates:** "Your blade flashes (**rolled 18 vs AC 15**). Steel bites deep into the goblin's shoulder—**7 damage**—and it staggers back with a shriek."

### Procedural Generation

**Player (Bob):** "I talk to the innkeeper."

**DM:**
1. Loads `/worldbuilding` skill
2. Generates NPC on-the-fly:
   - Name: "Gareth Stone"
   - Personality: "Gruff but fair"
   - Secret: "Owes money to thieves' guild"
3. Saves to `world/npcs/gareth-stone.json`
4. Roleplays the innkeeper

Later, if players return, the same innkeeper is there (loaded from file).

## Campaign Management

### Creating a New Campaign

1. Copy the template:
   ```bash
   cp -r campaigns/template campaigns/my-new-campaign
   ```

2. Edit `campaigns/my-new-campaign/config.json`:
   ```json
   {
     "campaign_name": "My Epic Adventure",
     "tone": "Dark Fantasy",
     "max_players": 4
   }
   ```

3. Update `campaigns/active.json`:
   ```json
   {
     "active_campaign_path": "campaigns/my-new-campaign"
   }
   ```

### Adding Players

Create a player file in `campaigns/{campaign}/players/{id}.json`:
```json
{
  "player_id": "player3",
  "player_name": "Charlie",
  "characters_controlled": ["gimli"],
  "permissions": {
    "can_edit_own_characters": true,
    "can_view_other_sheets": false,
    "can_edit_world": false
  }
}
```

Then create their character sheet in `campaigns/{campaign}/characters/gimli.json` using the character schema.

### Session Management

**Start of session:**
- DM reads `state.json` and recaps last session
- Updates `session_players_present` in state.json

**During session:**
- All HP, inventory, quest progress saved to files
- NPCs and locations generated are written to world/

**End of session:**
- Update `session_log.md` with key events
- Ensure all changes are saved

## Architecture

### Why This Works

**Agentic Coders Excel At:**
- Reading/writing files (character sheets, world state)
- Orchestrating tools (API calls, dice rolls)
- Creative narrative (describing scenes, NPC dialogue)
- Progressive loading (skills only when needed)

**Agentic Coders Struggle With:**
- Memorizing rules (→ solved with API)
- Arithmetic (→ solved with roll-cli)
- Remembering HP across sessions (→ solved with files)

### Design Principles

1. **File System is Truth** - Never rely on context memory
2. **Tools for Rules** - Never hallucinate mechanics
3. **Progressive Skills** - Load only what's needed
4. **Multi-Player Awareness** - Respect player boundaries
5. **Narrative First** - Mechanics serve the story

## Extending DungeonOS

### Adding New Skills

Use the `/skill-creator` skill in the parent directory:
```
/skill-creator Create a skill for handling social encounters
```

Skills should be self-contained with clear triggering conditions.

### Custom Scripts

Add Python scripts to `/scripts/` for:
- Campaign initialization
- Batch NPC generation
- State validation
- Session recap generation

Use `uv` to manage dependencies.

### Additional Systems

DungeonOS is designed for D&D 5e but can be adapted:
- Update API endpoints for other systems
- Modify schemas for different character formats
- Create system-specific skills

## Troubleshooting

### Dice roller not found

Activate the virtual environment:
```bash
source .venv/bin/activate
roll 1d20+5 -v
```

Or install roll-cli:
```bash
uv pip install roll-cli
```

### API returns 404

The D&D 5e API moved to `/api/2014/` endpoint. Ensure curl commands use:
```bash
curl -sL "https://www.dnd5eapi.co/api/2014/spells/{spell-name}"
```

Note the `-L` flag to follow redirects.

### Skills not loading

Ensure you're in the `/dungeon-os/` directory:
```bash
pwd  # Should show .../dungeon-os
```

Skills are discovered from `./.claude/skills/`.

### Character HP not persisting

Verify the DM is using the Edit tool to update character files, not just narrating changes.

Check `campaigns/{campaign}/characters/{name}.json` to see if HP actually changed.

## Credits & Philosophy

DungeonOS is inspired by the realization that AI agents are excellent **orchestrators** but poor **calculators**. By embracing file-based state, external tools, and progressive skill loading, we transform general-purpose agents into specialized Dungeon Masters.

**Core Philosophy:**
- Leverage native capabilities (file editing, tool use)
- Offload non-creative tasks (dice, rules lookup)
- Keep context lean (progressive skill loading)
- Persist everything (files outlive conversations)

## Next Steps

1. Play the example campaign
2. Create your own campaign
3. Add more skills (exploration, social, magic)
4. Customize character creation
5. Build custom NPC/loot generators

**Welcome to DungeonOS. Roll for initiative.**