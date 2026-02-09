# dungeon-os

This is the main repository for Dungeon OS, an open-source operating system for Dungeons and Dragons.

This outer folder is for the development of the Dungeon OS kernel, enter the `dungeon-os` folder to experience the Dungeon OS userland.

## DND-API Wrapper

The project includes a Python CLI wrapper (`dnd-api`) for efficient D&D 5e API access with caching and DM utilities:

```bash
# Install
uv pip install -e .

# Use wrapper
uv run dnd-api list monsters
uv run dnd-api get monsters/goblin
uv run dnd-api search spells --level 3 --school evocation
uv run dnd-api random monsters --count 3
uv run dnd-api info conditions paralyzed
```

**Benefits:**
- Caching: First call ~200ms (API), subsequent calls ~30ms (cached)
- Token efficiency: 35-45% reduction in token usage per session
- Search: Filter monsters by CR, spells by school/level, equipment by category
- DM utilities: Random selection, quick reference formatting

See `dnd_api/README.md` for full documentation.