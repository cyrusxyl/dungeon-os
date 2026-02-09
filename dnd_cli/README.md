# dnd-cli Wrapper

A Python CLI wrapper for the D&D 5e API with caching, semantic search, and DM utilities.

## Installation

```bash
cd dungeon-os
uv pip install -e .
```

## Quick Start

```bash
# First time: Warmup cache for fast searches
uv run dnd-cli warmup monsters
uv run dnd-cli warmup spells

# List all monsters
uv run dnd-cli list monsters

# Get specific monster (cached)
uv run dnd-cli get monsters/goblin

# Search with fuzzy matching (handles typos!)
uv run dnd-cli search monsters --name "gobln"  # Finds "Goblin"
uv run dnd-cli search spells --name "firbal"   # Finds "Fireball"

# Search for spells
uv run dnd-cli search spells --level 3 --school evocation

# Text search in descriptions
uv run dnd-cli search monsters --text "invisible"

# Random encounter
uv run dnd-cli random monsters --count 3

# Quick reference
uv run dnd-cli info conditions paralyzed
```

## Commands

### list

Browse all available resources:

```bash
uv run dnd-cli list <resource>
```

**Supported resources**: `monsters`, `spells`, `equipment`, `magic-items`, `classes`, `races`, `backgrounds`, `feats`, `conditions`, `damage-types`, `skills`, `languages`, `ability-scores`, `proficiencies`, `weapon-properties`

### get

Fetch specific resource with caching:

```bash
uv run dnd-cli get <endpoint>
uv run dnd-cli get <endpoint> --json  # Raw JSON output
```

**Examples**:
```bash
uv run dnd-cli get monsters/goblin
uv run dnd-cli get spells/fireball
uv run dnd-cli get equipment/longsword
uv run dnd-cli get classes/wizard/levels/5
```

**Extract minimal fields with jq**:
```bash
uv run dnd-cli get monsters/goblin --json | jq '{name, hp: .hit_points, ac: .armor_class[0].value}'
```

### search

**Fuzzy search with filters** (requires warmup):

```bash
uv run dnd-cli search <resource> [--filters]
```

**Monster filters**:
- `--name <query>` - **Fuzzy name matching** (handles typos: "gobln" → "Goblin")
- `--text <query>` - **Text search** in abilities/descriptions
- `--cr <range>` - Challenge rating (e.g., `5`, `5-7`, `3+`)
- `--type <type>` - Creature type (undead, dragon, humanoid, etc.)
- `--size <size>` - Size (tiny, small, medium, large, huge, gargantuan)

**Spell filters**:
- `--name <query>` - **Fuzzy name matching** (handles typos: "firbal" → "Fireball")
- `--text <query>` - **Text search** in spell descriptions
- `--level <range>` - Spell level (0-9 or cantrip)
- `--school <school>` - School of magic (evocation, enchantment, etc.)
- `--class <class>` - Available to class (wizard, cleric, etc.)

**Equipment filters**:
- `--name <query>` - **Fuzzy name matching** (handles typos: "longswrd" → "Longsword")
- `--category <category>` - Category (weapon, armor, adventuring-gear)

**Examples**:
```bash
# Fuzzy name matching (typo-tolerant)
uv run dnd-cli search monsters --name "gobln"
uv run dnd-cli search spells --name "firbal"
uv run dnd-cli search equipment --name "longswrd"

# Partial name matching
uv run dnd-cli search monsters --name "dra"  # Finds all dragons
uv run dnd-cli search spells --name "fir"    # Finds fire spells

# Text search in descriptions
uv run dnd-cli search monsters --text "invisible"
uv run dnd-cli search spells --text "fire damage"
uv run dnd-cli search monsters --text "bonus action"

# Structured filters
uv run dnd-cli search monsters --cr 5-7 --type undead
uv run dnd-cli search spells --level 3 --school evocation

# Combined filters
uv run dnd-cli search monsters --cr 0-2 --text "bonus action"
uv run dnd-cli search spells --level 3 --school evocation --text "fire"
```

### random

Random selection from resources:

```bash
uv run dnd-cli random <resource> --count <n>
```

**Examples**:
```bash
uv run dnd-cli random monsters --count 3
uv run dnd-cli random spells --level 1-3 --count 2
uv run dnd-cli random equipment --category weapon --count 1
```

### info

Quick reference lookup with formatted output:

```bash
uv run dnd-cli info <resource> <index>
```

**Supported resources**: `conditions`, `skills`, `damage-types`, `weapon-properties`

**Examples**:
```bash
uv run dnd-cli info conditions paralyzed
uv run dnd-cli info skills stealth
uv run dnd-cli info damage-types fire
```

### cache-info

Display cache statistics:

```bash
uv run dnd-cli cache-info
```

### warmup

Pre-cache full resource data for fuzzy search and filtering:

```bash
uv run dnd-cli warmup <resource>        # Warmup specific resource
uv run dnd-cli warmup all               # Warmup all resources
uv run dnd-cli warmup monsters --force  # Force re-fetch
```

**Note:** Run warmup before using search filters (`--cr`, `--type`, `--level`, `--text`, etc.). Warmup caches full resource data, enabling fast filtering.

**Examples**:
```bash
uv run dnd-cli warmup monsters  # ~1-2 minutes for 334 monsters
uv run dnd-cli warmup spells    # ~1-2 minutes for 319 spells
uv run dnd-cli warmup all       # ~3-5 minutes total
```

### clear-cache

Clear cache files:

```bash
uv run dnd-cli clear-cache              # Clear all
uv run dnd-cli clear-cache monsters     # Clear specific resource
```

## Caching & Search

**Cache location**: `{campaign}/.cache/api/2014/`

**Performance**:
- First lookup: ~200-300ms (API call)
- Cached lookup: ~30-50ms (file read)
- Search (after warmup): < 100ms (in-memory)

**Token efficiency**:
- List workflows: 35-45% reduction
- Search workflows: 90% reduction (fuzzy search prevents listing all items)

**Fuzzy search features**:
- Typo tolerance: "gobln" → "Goblin", "firbal" → "Fireball"
- Partial matching: "fir" → Fire Bolt, Fireball, Fire Shield
- Text search: Find keywords in abilities/descriptions
- Structured filters: CR ranges, types, levels, schools
- Combined filters: Mix multiple criteria

## Performance Comparison

**Without wrapper** (repeated API calls):
- 5 monster lookups: 5 × 500 tokens = 2,500 tokens
- 3 spell searches: 3 × 800 tokens = 2,400 tokens
- Total: 4,900 tokens

**With wrapper** (cached):
- 5 monster lookups: 500 + (4 × 100) = 900 tokens
- 3 spell searches: 3 × 150 = 450 tokens
- Total: 1,350 tokens (72% reduction)

## Architecture

```
dnd_cli/
├── __init__.py          # Package constants
├── __main__.py          # CLI entry point
├── api.py              # API wrapper with error handling
├── cache.py            # Cache management
├── cache_warmup.py     # Pre-fetch full resource data
├── fuzzy.py            # RapidFuzz-based fuzzy matching
├── text_search.py      # Text search in descriptions
└── commands/           # Command implementations
    ├── list.py
    ├── get.py
    ├── search.py       # Fuzzy search + filters + text
    ├── random.py
    ├── info.py
    └── cache_cmd.py
```

## Integration with Skills

All DungeonOS skills support the wrapper. Example from combat skill:

```bash
# Quick lookup (full data, cached)
uv run dnd-cli get monsters/goblin

# Extract minimal fields
uv run dnd-cli get monsters/goblin --json | jq '{name, hp: .hit_points}'

# Search for appropriate monster
uv run dnd-cli search monsters --name orc

# Random encounter
uv run dnd-cli random monsters --count 3
```

## Future Enhancements

Phase 3 (Content Generation):
- `generate npc` - NPC creation with personality
- `generate encounter` - Balanced encounter building
- `generate loot` - Treasure tables
- `generate quest` - Quest hooks
- `generate shop` - Merchant inventory

## See Also

- [D&D 5e API Documentation](https://www.dnd5eapi.co/docs/)
- DungeonOS CLAUDE.md - Full system documentation
- Skills documentation in `.claude/skills/`
