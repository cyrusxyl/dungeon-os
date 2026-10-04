"""The visual stage: a pixel-art scene, actors, and a dialogue box in a browser.

The DM agent drives the stage through `dnd-cli` commands. It never draws and
never gives pixel positions:

- `dnd-cli show beat` appends story events (scene, enter, say, ...) to
  `{campaign}/stage/events.ndjson`.
- `dnd-cli actor set` and `dnd-cli scene set` write structured specs to
  `{campaign}/stage/actors/` and `{campaign}/stage/scenes/`.
- `dnd-cli site set` and `dnd-cli map place` write sites (generated
  dungeons the party walks through) to `{campaign}/stage/sites/` and region
  and city maps to `{campaign}/stage/maps/`.

The stage server reads only `{campaign}/stage/` plus state.json and
characters/*.json. It never opens dm_story.md, canon.json, session_log.md, or
world/*. Events, actors and scenes are player-visible by design. Sites and
maps hold secrets (the whole layout, hidden places), so the server sends the
browser only what the party has seen or been told.
"""
