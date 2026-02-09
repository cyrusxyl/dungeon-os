# dungeon-os

This is the main repository for Dungeon OS, an open-source operating system for Dungeons and Dragons.

This outer folder is for the development of the Dungeon OS kernel, enter the `dungeon-os` folder to experience the Dungeon OS userland.

## DND-API Wrapper

The project includes a Python CLI wrapper (`dnd-api`) for efficient D&D 5e API access with caching and DM utilities:

```bash
# Install
uv sync

# First time: Warmup cache for fast searches
uv run dnd-api warmup monsters
uv run dnd-api warmup spells

# Use wrapper
uv run dnd-api list monsters
uv run dnd-api get monsters/goblin

# Search with fuzzy matching (handles typos!)
uv run dnd-api search monsters --name "gobln"  # Finds "Goblin"
uv run dnd-api search spells --name "firbal"   # Finds "Fireball"

# Filter by attributes
uv run dnd-api search monsters --cr 5-7 --type undead
uv run dnd-api search spells --level 3 --school evocation

# Text search in descriptions
uv run dnd-api search monsters --text "invisible"
uv run dnd-api search spells --text "fire damage"

# Combined filters
uv run dnd-api search monsters --cr 0-2 --text "bonus action"

# Other utilities
uv run dnd-api random monsters --count 3
uv run dnd-api info conditions paralyzed
```

**Features:**
- **Fuzzy Search**: Typo-tolerant name matching ("gobln" → "Goblin")
- **Structured Filters**: CR ranges, type, size, level, school, class
- **Text Search**: Find keywords in abilities/descriptions
- **Caching**: First call ~200ms (API), subsequent calls ~30ms (cached)
- **Token Efficiency**: 90% reduction in token usage for search workflows
- **DM Utilities**: Random selection, quick reference formatting

See `dnd_api/README.md` for full documentation.