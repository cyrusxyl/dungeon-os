# dungeon-os

This is the main repository for Dungeon OS, an open-source operating system for Dungeons and Dragons.

This outer folder is for the development of the Dungeon OS kernel, enter the `dungeon-os` folder to experience the Dungeon OS userland.

## dnd-cli Wrapper

The project includes a Python CLI wrapper (`dnd-cli`) for efficient D&D 5e API access with caching and DM utilities:

```bash
# Install
uv sync

# First time: Warmup cache for fast searches
uv run dnd-cli warmup monsters
uv run dnd-cli warmup spells

# Use wrapper
uv run dnd-cli list monsters
uv run dnd-cli get monsters/goblin

# Search with fuzzy matching (handles typos!)
uv run dnd-cli search monsters --name "gobln"  # Finds "Goblin"
uv run dnd-cli search spells --name "firbal"   # Finds "Fireball"

# Filter by attributes
uv run dnd-cli search monsters --cr 5-7 --type undead
uv run dnd-cli search spells --level 3 --school evocation

# Text search in descriptions
uv run dnd-cli search monsters --text "invisible"
uv run dnd-cli search spells --text "fire damage"

# Combined filters
uv run dnd-cli search monsters --cr 0-2 --text "bonus action"

# Other utilities
uv run dnd-cli random monsters --count 3
uv run dnd-cli info conditions paralyzed
```

**Features:**
- **Fuzzy Search**: Typo-tolerant name matching ("gobln" → "Goblin")
- **Structured Filters**: CR ranges, type, size, level, school, class
- **Text Search**: Find keywords in abilities/descriptions
- **Caching**: First call ~200ms (API), subsequent calls ~30ms (cached)
- **Token Efficiency**: 90% reduction in token usage for search workflows
- **DM Utilities**: Random selection, quick reference formatting

See `dnd_cli/README.md` for full documentation.