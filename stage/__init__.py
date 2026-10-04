"""The visual stage: a pixel-art scene, actors, and a dialogue box in a browser.

The DM agent drives the stage through `dnd-cli` commands. It never draws and
never gives pixel positions:

- `dnd-cli show beat` appends story events (scene, enter, say, ...) to
  `{campaign}/stage/events.ndjson`.
- `dnd-cli actor set` and `dnd-cli scene set` write structured specs to
  `{campaign}/stage/actors/` and `{campaign}/stage/scenes/`.

Everything under `{campaign}/stage/` is player-visible by design. The stage
server reads only that directory plus state.json and characters/*.json. It
never opens dm_story.md, canon.json, session_log.md, or world/*.
"""
