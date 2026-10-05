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

Rolls play in a window modelled on Baldur's Gate 3: the title and the DC, a
d20 that tumbles, one tile for every number that adds to it (ability,
proficiency, expertise, a Guidance die), and the result. With advantage or
disadvantage two dice roll and the lower or higher one drops away. A fireball
shows one row per creature. When the DM asks a player character for a check
(`@roll`), the window waits for the player: add a bonus (Guidance, Bless,
Bardic Inspiration, advantage...), leave one off, and click **Roll**. The
party panel shows the turn order, each character's action, bonus action and
reaction, spell slots, class resources (Rage, Ki, Second Wind...),
concentration and conditions. **Sheet** opens the abilities and skills, the
inventory and the spellbook. The DM adds bonuses with `dnd-cli effect add`.

The **Map** button shows the current level of the world (a dungeon, a city,
a region) and the levels above it; pick a known place to travel there. In a
dungeon or building (`dnd-cli site set`, `@explore`), the party walks a
generated floor plan with the arrow keys, WASD, or a click. Sight, fog, and
wandering-monster checks run in the stage; the DM is called only when the
party finds something. Design: `dungeon-crawl.md`.

**New Game** asks for a name, an optional pitch, and who makes the party:
the player (default) or the DM, from the pitch (for example, the characters
of a known story). While the DM builds the world in the background, the game
view shows the character creation screen. The player makes one or more
characters there, then clicks **Begin adventure**. The DM then opens the first
scene with the new party. The **New character** button in the party panel
opens the same screen for a new player who joins a running campaign.

The first launch builds the web UI with npm (Node 22+) and downloads the
pixel art (~135 MB: Universal LPC, LPC tile and prop packs from OpenGameArt,
and CC0 Dungeon Crawl tiles) into the git-ignored `assets/` folder. The art is not redistributed; credits files are
kept next to it.

In `--classic` mode, the start menu runs the DM in a real terminal on the
left, with a live state and character panel on the right.

- **Resume** continues the active campaign (the last one played). On the
  visual stage it offers two ways: **Continue** keeps the DM's own conversation
  (`claude --resume`, or `agy --conversation`), so the DM does not read the
  skills and files again and the first answer is faster; **New DM session**
  starts a fresh DM that reads the game files (`state.json`, `session_log.md`,
  `canon.json`). Continue is offered only when the saved conversation still
  exists for the agent now set. The stage learns the conversation id from its
  hook. The Restart button after a DM crash continues the conversation too.
- **Load Game** picks any campaign under `game/campaigns/`, with the same two
  ways to start it, and its **saves** (below).
- **New Game** names a brand-new campaign, scaffolds it from the template,
  and starts Session Zero.
- **Settings** picks the agent framework and model, saved to
  `game/settings.json` (per machine, git-ignored).

## Saves

Every campaign folder is its own git repository (`dnd_cli/saves.py`, git must
be on PATH). The stage saves after each DM turn, and once when a game starts.
The **Save** button in the game view makes a named save (while the DM is
idle). **Load Game**, then a campaign, lists the saves; **Load** puts the files
(including the stage log) back to that point and starts a new DM session,
because the old conversation remembers what came later. A load never loses the
present: the current state is saved first, and the load is a new commit on top.
To look at the history by hand: `git -C game/campaigns/<slug> log`.

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
## Development

- `.venv/bin/python tests/run_all.py` runs every test suite (about 15 seconds). Add `--visual` to also run the browser check of the roll window (needs Google Chrome, and `npm run build` in `stage/web`).
- `tests/test_rolls_fuzz.py` audits 400 random rolls: the total, the dice, the effects, the outcome, and that no hidden number reaches the stage.
- `tests/visual_roll_window.py [dir]` drives headless Chrome through the roll window. It checks what unit tests cannot: the window closes on time while the DM keeps sending events, the Roll button waits for unread story, and a hidden DC is not in the page. Give it a directory to keep screenshots.
- A test that cannot fail proves nothing. After you add a check, break the code on purpose and see the check fail.
- Stop a dev server with `fuser -k <port>/tcp`. Do not use `pkill -f`: it can kill your own shell.
- The DM's rules are in `game/AGENTS.md`. `CLAUDE.md`, `GEMINI.md` and `WARP.md` in `game/` are links to it. The DM runs in `game/`, so it also loads any `CLAUDE.md` above that folder. Keep developer notes here in the README, not in a `CLAUDE.md`.
- The web UI is the default view. `--classic` is the older Textual view.
