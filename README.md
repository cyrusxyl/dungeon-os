# dungeon-os

This is the main repository for Dungeon OS, an open-source operating system for Dungeons and Dragons.

This outer folder is for the development of the Dungeon OS kernel, enter the `dungeon-os` folder to experience the Dungeon OS userland.

## Playing

```bash
uv run dungeon-os            # visual stage in a browser: Resume, Load Game, New Game, Settings
uv run dungeon-os <slug>     # skip the menu, start that campaign directly
uv run dungeon-os --classic  # earlier terminal view with the same menu
```

The visual stage runs the DM (`claude` by default) in a terminal that the
stage server owns, and shows the game in a pixel-art web page: the room, the
characters in it, a dialogue box with portraits, dice rolls, choice buttons,
the party panel, and a Log of the story so far. The DM drives it with
`dnd-cli show beat`, `dnd-cli actor set` and `dnd-cli scene set` (see the
`stage` skill in `game/.claude/skills/`). Looks of characters and places are
saved per campaign and reused. A browser reload reconnects to the same DM
session; the Menu button ends it. The DM's raw terminal is in the Console
drawer.

The **Map** button shows the current level of the world (a dungeon, a city,
a region) and the levels above it; pick a known place to travel there. In a
dungeon or building (`dnd-cli site set`, `@explore`), the party walks a
generated floor plan with the arrow keys, WASD, or a click. Sight, fog, and
wandering-monster checks run in the stage; the DM is called only when the
party finds something. Design: `dungeon-crawl.md`.

The first launch builds the web UI with npm (Node 22+) and downloads the
pixel art (~130 MB, Universal LPC and CC0 Dungeon Crawl tiles) into the
git-ignored `assets/` folder. The art is not redistributed; credits files are
kept next to it.

In `--classic` mode, the start menu runs the DM in a real terminal on the
left, with a live state and character panel on the right.

- **Resume** continues the active campaign (the last one played) from its game
  files (`state.json`, `session_log.md`, `canon.json`). It starts a fresh DM
  session that reads those files — it does not need a saved conversation.
- **Load Game** picks any other saved campaign under `game/campaigns/` and
  plays it the same way.
- **New Game** names a brand-new campaign, scaffolds it from the template,
  and starts Session Zero.
- **Settings** picks the agent framework and model, saved to
  `game/settings.json` (per machine, git-ignored).

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