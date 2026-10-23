# Blocks

Built 2026-10-22. Prototype: https://claude.ai/artifact/T8sSdoaXBcZTaSwA8uC7zi. See also `compact-set.md`.

## What a block is
- A few cells in a room, each one of four heights: `block_low` (14 px, 3 ft, half cover), `block_half` (28 px, 5 ft, three-quarters cover), `block_tall` (48 px, 10 ft, stops sight), `block_pillar` (64 px, 15 ft, stops sight).
- Each cell is a prop of the room (`slot: "block"`). The board already reads props for movement, cover and sight, so blocks need no new rule.
- A block can be 1 to 4 cells. Some are steps or stairs of mixed height. About 45 out of 100 stand against a wall.
- The floor left must stay in one piece. Blocks keep one cell from props, doors and each other.
- Heights only change the look, cover and sight. There is no climbing or jumping yet. The heights are in feet in `stage/blocks.py` so such rules can use them later.

## Where they come from
- `stage/blocks.py` makes them (pure, seeded). `scenes.room(spec, full=True)` makes them for the full room. The story set (`scenes.room(spec)`) shows the same blocks at their scaled places, one cell each, tall and big first (`blocks.fit`). A set that is the full room (the plain 14 x 11 room) has the same blocks.
- The spec has `blocks` (`auto`, or 0 to 24) and `heights` (`mixed`, `low`, `tall`). `scene set` takes `blocks=` and `heights=`. A new place gets `blocks=auto`. A place saved before this has no `blocks` key and no blocks.
- `auto` is one block for each `density` floor cells. The density, the skin and the colors come from the `blocks` table of `stage/data/arena.json`, by the theme of the scene template.
- Skins: `flat` (a color), `wall` (the wall tile on the sides and top), `floor` (the wall tile on the sides, the floor tile on top). A place with no walls is always flat.

## Drawing
- `lib/blocks.ts` draws a block cell in depth order. The tiles come from the room sheet (`room.png`): the floor tile of the cell, and the wall strip. No new art.
- A block of 28 px or more in front of a figure fades to 30% (`lib/blockMap.ts`), in the scene and on the board. The same code serves both.

## Not built
- Blocks in arenas that are not in a scene room (a site, or a room the stage made).
- A ghost ring for a figure hidden by a wall stub or a tall prop.
- Walking or jumping onto blocks.
