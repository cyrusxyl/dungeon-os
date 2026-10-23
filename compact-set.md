# Compact set: plan

**Status: built 2026-10-21.** The real code differed from the demo. A scene room is a random shape and size, and a fight in a scene already used the scene room (`_in_room`). So the change is: the set is the same room squeezed to 12 × 9 (`rooms.shrink`, `scenes.room(spec)`); the fight uses the full room (`scenes.room(spec, full=True)`). `cast.scale_cell` maps cells between the two (floor box to floor box). Fixed 14 × 11 rooms are their own set. Walking is removed. The click menu (talk, look, go through) is in `StageView`. Tests: `tests/test_set.py`. Not built: `Stage.stand_up` is removed with walking (a seated character stays seated); an exit prop for scenes with no door decor.

Decided 2026-10-21. Demo: https://claude.ai/artifact/4dCrHDM4P4iASVMWvobujF
Start the build in a NEW session. Read this file first. See also `isometric-view.md`.

## Problem

- The scene and the arena share one iso view. The arena is large.
- In a story scene the camera must show the whole arena. The tiles are small. The player cannot read or click them.
- Scene walking has no gameplay purpose. The DM drives the story, talk, and place changes.

## Decision

- The scene becomes a **set**: a small room sized to the cast. The camera fits the set.
- No player or NPC walking in a scene.
- The full arena is built only when a fight starts.
- One iso renderer stays. The legacy 2D scene does not return.
- BG3-style free exploration is not planned. The DM keeps the story. This plan does not block it later.

## Rules

1. **Two sizes from one scene spec.** The spec gives a set size and a full size. Props keep their slots and their size in cells. Props sit at the same relative place in both rooms.
2. **Set placement.** `cast.place` places the actors in the set. This rule does not change.
3. **Fight placement.** The arena is built from the same spec at full size. Each actor keeps its relative spot: scale the set cell to the full room, then take the nearest free cell. Keep the spacing rule. Bystanders stay near their props and block cells. Actors with no set cell (fight-only foes) join from the far side.
4. **Cover.** The arena may add cover that the set does not show. Place actors on free cells only.
5. **After a fight.** Do not copy arena cells back. The set is placed again with rule 2. The `arena_end` event still carries `down` and `sides`.
6. **Camera.** Scene: fit to the set. Fight: follow the active creature (already built).
7. **Click actions.** Click a person: menu "Talk to X" and "Look at X". Click an exit: "Go through X". Each click posts text to the DM like a typed action. The server does not change the scene by itself.

## Work

### Remove
- `stage/walk.py` (180 lines).
- In `stage/server.py`: `Stage.walk_tick`, `broadcast_cells`, `save_cells`, their calls in `tail` and `settle`, the `/api/scene/walk` route and handler, the `with_cells` call at start.
- In `stage/state.py`: `with_cells` (line 223) and its call.
- `stage/cells.json` file handling.
- Browser: the `cells` message in `lib/stage.ts`, `onCell` in `SceneCanvas.tsx`, `walkAs` in `StageView.tsx` and `GameView.tsx`.
- Tests: `tests/test_walk.py`, `tests/test_scene_walk.py`, `tests/visual_walk.py` (438 lines).
- The `@walk` beat line in the DM skill text. Check `SKILL.md`.

### Keep as no-op
- Old `walk` events in `events.ndjson` (the Pi game has them). The refold must accept them and ignore them. Add a test.

### Change
- `stage/arena.py` `source_of` (line 452 on): build the full room. Place with rule 3. Remove the use of scene actor cells as fight cells.
- `stage/scenes.py`: add the set size (see "Open items").
- `stage/cast.py`: add a function that maps set cells to a full room.
- `Stage.stand_up`: it loses its trigger (a seated PC ordered to walk). Drop it, or give it a new trigger. Decide in the build session.
- `stage/web/src`: `SceneCanvas` and the arena view use the fit camera for the set. Check the fight view with the new start cells.
- `view/` or other docs that describe scene walking: update.

### Add
- Click menu in the set (person and exit). Post to the existing act route. Do not add a new server route.
- A way to find the exit cell of a scene in the set (the demo uses the west wall door).
- Tests: set placement, scale mapping, free-cell fallback, fight start from a set, old `walk` event refold, click action text.

## Open items (decide in the build session)
- How the set size comes from the full room: a smaller generated room from the same spec, with slot props kept (chosen). The room shape generator in `iso-prototype/rooms.js` needs a "set" size class. Check that every shape still gives a valid room at small size.
- Size rule: set cells = roughly 2 to 3 cells per actor, minimum about 7×6. Test with 2, 6, and 12 actors.
- A fight in a scene with no table or bar (open ground): same rule.
- `Stage.stand_up` (see above).
- Exits drawn on the wall: the demo glows the door. The real art needs an exit prop or a wall door.

## Order of work
1. Tests first: scale mapping and refold of old `walk` events.
2. Set size in the scene spec and `source_of` with rule 3.
3. Remove walking (server, state, browser, tests).
4. Click menu in the set.
5. Camera fit check on phone and desktop. Send a screenshot for each visual change.
6. Run the full test suite. Deploy to the Pi only after the user agrees (a restart ends the running game).

## Done when
- A scene shows a readable set at tile size of about 80 px on desktop.
- A fight starts with actors near their set spots.
- No walking code remains. The old log still loads.
