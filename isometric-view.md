# Isometric view

Plan to draw the stage and the combat arena in a 2:1 isometric view. One renderer draws both. This file holds the decisions, the geometry, the data, and the work in order. A new session can build from this file alone.

## Status (2026-10-17): built, not committed

All six steps are built. The files `iso-prototype/bands.js` and `iso-prototype/rooms.js` are ported (`stage/web/src/lib/props.ts`, `iso.ts`, `stage/rooms.py`) and can be deleted when the owner agrees. Where the build differs from the plan, the owner agreed in this session:

- **Stand and sit points** are not whole cells. Each point is projected through the pose of its prop (`pointOn` in `lib/scene.ts`), so an actor sits on the seat or stands on the table top. The data keeps the cell of the prop and the points in pixels of its picture.
- **A fight from a scene** is fought in the room of that scene (`stage/arena.py` `_in_room`), with every actor on the cell the server gave it in the scene (`stage/cast.py` places; `Stage.settle` keeps the cell on the actor through a logged `place` event; there is no second copy in the browser). A scene can have a room of any shape (`shape=`, `seed=`, `size=` on `scene set`); the default is still the 10 x 8 room.
- **`scenes.render()` and `scene preview` are removed.** There is no flat picture of a scene.
- **Furniture in a wall slot** (a cabinet, a dresser) stands on the floor in its tuned pose. Only wall pieces hang on the wall.
- **Top strip** of a prop: only when the whole chain starts with a vertical band (as `bands.js` does). **Back walls:** every uncut wall draws first. **Never-seen cells** count as floor in the cut rule. A tall wall shows its face beside a low rim.
- **Room shapes** are in `stage/rooms.py`, not in `arena.py`. The theme odds are in `stage/data/arena.json`.
- **The forest** still has wall blocks (of its look), not trees on the rim.
- **Mood** is a CSS filter on the canvas. The rain, snow and fog effects of the old picture are gone.

These files were added for the work and are not committed: `isometric-view.md` (this file), `stage/data/prop_poses.json`, `iso-prototype/`, `stage/rooms.py`, `stage/cast.py`, `stage/web/src/lib/{iso,props,scene,propAtlas,roomDraw}.ts`, `stage/web/src/components/SceneCanvas.tsx`, the checks and tests named `*iso*`, `*cast*`, `*scene*`, `*props*`.

The text below is the plan as written before the build.

The prototypes ran as browser demos (artifacts). They used the real game art. They were tuned by the owner by eye. Do not change the look rules in this file without asking the owner.

## Goal

- The arena and the scene use one view: 2:1 isometric, 45 degrees, from above.
- The art does not change. The view uses the LPC tiles, the LPC actor sprites, the DCSS monsters and the existing props. It transforms them.
- Room shapes are made by code. The DM does not have to describe the shape.
- The server rules do not change. Walking, sight, reach and cover stay in Python (`stage/arena.py`, `stage/board.py`). Only the drawing and the room data change.
- A fight starts in the same room as the scene. The party stays on its tiles. This closes "Return" in `combat-board.md`.

## Decisions (agreed with the owner, 2026-10-17)

1. **Floors:** draw each floor tile with a canvas transform. No baked tiles.
2. **Near walls** (south and east): draw a low rim. See "Wall cut rule".
3. **One renderer** for the scene and the arena. A scene is a small room grid with props. Combat adds overlays.
4. **Walls** are blocks: a top cap and two sheared faces. Wall decor (window, fireplace, tapestry, sign) is sheared onto the wall face.
5. **Props** use one method: bands. See "Prop poses". The pose of every prop is in `stage/data/prop_poses.json`.
6. **Shading** is fixed for every prop: side 0.62, top 1.22, slab 0.6. There are no shading settings.
7. **Room shapes** come from code with a seed. Rooms have a random size and a random orientation. A theme sets the odds. The DM can still ask with a new word `shape=`.
8. **Scope:** the dungeon crawl view (`CrawlView.tsx`, `stage/crawl.py`) is not in this plan.
9. **Do not commit** until the owner asks.

## Reference demos

The owner approved these. Open them for the target look. The links may need the owner to share them.

- Main demo: https://claude.ai/artifact/8KsUL42c34fPKdcW7utCDx (arena and scene in one renderer)
- Room lab: https://claude.ai/artifact/RrQ5JV3nYKtzNGG8VjCwyt (17 shapes, reroll, size and orientation)
- Prop tuner: https://claude.ai/artifact/KvgeSm6P47jGNdU1RGLfAy (all 284 props, approved)

## Geometry

Use one cell size. A floor tile is 32 px in the art. On the screen a cell is a diamond, 64 px wide and 32 px high. Sprites keep their size (actor frame 64 x 64).

- **Cell to screen.** The top corner of cell (x, y) is `P = (ox + (x - y) * 32, oy + (x + y) * 16)`. The ground centre is `P + (0, 16)`. Actors and props stand with their feet on the ground centre. An actor frame has its feet row at 60, so draw it at `(cx - 32, cy - 60)` (see `FEET_ROW` in `StageView.tsx`).
- **Screen to cell** (mouse and touch picking). With `mx, my` relative to `(ox, oy)`: `gx = (mx / 32 + my / 16) / 2` and `gy = (my / 16 - mx / 32) / 2`. The cell is `floor(gx), floor(gy)`. A tall sprite does not change picking. Picking uses only the floor cell under the pointer.
- **Canvas size.** `W = (w + h) * 32 + 16`. `ox = h * 32 + 8`. `oy = wallH + 70`. `H = oy + (w + h) * 16 + 36`. Draw on a canvas of `W * 2` by `H * 2` and scale the context by 2. Show it scaled to the container width with `image-rendering: pixelated`.
- **Floor tile.** `setTransform(S, S/2, -S, S/2, S*px, S*py)`, then draw the 32 px tile at size 32.7 (the extra 0.7 hides seams). `S` is 2.
- **Depth order.** Sort by `x + y`. A wall block uses `x + y - 0.4`. A unit uses `x + y + 0.01`. A back wall (the north row and the west column) always draws first.
- **Wall block** of height `h` at cell (x, y), top corner `(px, py)`:
  - Top cap: `setTransform(S, S/2, -S, S/2, S*px, S*(py - h))`. Draw the wall texture, then a light overlay `rgba(255,240,220,0.16)`.
  - Face toward +y (draw when cell (x, y+1) is not a wall): `setTransform(S, S/2, 0, S, S*(px - 32), S*(py + 16 - h))`. Darken with `rgba(8,4,16,0.22)`.
  - Face toward +x (draw when cell (x+1, y) is not a wall): `setTransform(S, -S/2, 0, S, S*px, S*(py + 32 - h))`. Darken with `rgba(8,4,16,0.42)`.
  - Full height is 48. A texture shorter than the height is drawn as two stacked tiles (see `iso-prototype/rooms.js`). A door tile draws on the +x face of a west wall.
- **Wall cut rule.** Cut a wall cell to height 12 if floor lies at (x-1, y), (x, y-1) or (x-1, y-1). Such a wall stands in front of floor and would hide units. Other wall cells keep full height. This one rule works for every room shape.
- **Wall decor.** Shear the picture along the wall. On the north wall use `setTransform(S, S/2, 0, S, ...)`. On the west wall use `setTransform(S, -S/2, 0, S, ...)`. One cell is 32 px along the wall. A decor item can sit above the floor (a window, a clock). The prototype lifted the window 14, the cabinet 18, the tapestry 6 and the fireplace 0.
- **Actor facing.** LPC has 4 facings. Map a move `(dx, dy)` with `sx = dx - dy` and `sy = dx + dy`: `sy < 0` is up, else `sx < 0` is left, else `sx > 0` is right, else down. Some turns look a little off. This is accepted.
- **Overlays** are diamonds drawn in the floor layer: walk range (blue, alpha 0.16 with a stroke), aim area (orange), hover (white outline), the current unit (gold outline). Reset the transform before sprites, health bars and intent labels.
- **Speed.** Do not redraw the floor and the walls for each frame. Draw them once into an offscreen canvas. Redraw it only when the room or the fog changes. Draw units, props and overlays on top. Cache each baked prop (see below).

## Prop poses

A prop is one picture. The picture is cut into 1 to 4 bands from the top down. A band is vertical (V) or horizontal (H). The bands alternate. The first band starts at the back. A prop that needs no transform is `upright`.

- **Vertical band** (rows `rs` to `re`): it stands up. Size scales its height. Thickness is how far it goes back (a made side face).
- **Horizontal band:** it lies flat. Size scales its depth toward the viewer. Thickness is how far it drops down (a made side face).
- **Chain.** A vertical band hangs from the current edge. A horizontal band lies forward from the current edge. The chain starts with `z` equal to the sum of the vertical heights and `vp = 0`. After a vertical band, `z -= rows * size`. After a horizontal band, `vp += rows * size`.
- **Matrices** (logical units, then multiplied by 2 for the canvas). With `k` the fit scale (at most 1) and `ws` the width:
  - Vertical: `T(k*ws, 0.5*k*ws, 0, k*size, e, f)` with `e = Ox - k*vp` and `f = Oy + 0.5*k*vp - k*z - k*size*rs`.
  - Horizontal: `T(k*ws, 0.5*k*ws, -k*size, 0.5*k*size, e, f)` with `e = Ox - k*vp + k*size*rs` and `f = Oy + 0.5*k*vp - 0.5*k*size*rs - k*z`.
  - Anchor: `Ox = cx - k*W/2 + k*Hpx/2 - k*vt/2` and `Oy = cy - 0.25*k*W - 0.25*k*Hpx + 0.25*k*vt + 4`. `W = w*ws`, `Hpx` is the sum of horizontal rows times size, `vt` is the largest vertical thickness.
- **Made faces.** Colour: the most common colour of the picture (5 bits per channel, luminance above 45). A vertical band sweeps its outline back by its thickness (one step is `(+1, -0.5)` px) in colour x 0.62. The first vertical band also sweeps a top strip (the first two rows of each column) in colour x 1.22. A horizontal band sweeps its outline down by its thickness in colour x 0.6, with the left half in colour x 0.78.
- **Draw order inside a prop:** all made faces first, then all original art in band order. A made face must never cover original art.
- **Facing.** A prop faces SW or SE. SE is the mirror of SW. Use SW first. Choose the face of a placed prop from a stable hash of its cell (about half SE). A wall decor item faces away from its wall.
- **Cache.** Build each prop pose once into an offscreen canvas per face. Draw the cache on the board.
- **Wall-mounted props** are one vertical band with thickness 0. A flat prop is one horizontal band with thickness 0.

### Data: `stage/data/prop_poses.json`

One record per prop name in `stage/data/scenery.json`. Two forms:

```json
"chest": { "pose": "upright" }
"cabinet": { "pose": "bands", "first": "H", "splits": [3], "bands": [[5, 0], [1, 15]], "width": 0.8 }
```

`splits` has one number fewer than `bands`. It is the row where each band ends. `bands` is `[size, thickness]` per band. `width` scales the picture along its own axis. The file has 284 records: 186 upright, 60 with one band, 25 with two bands, 8 with three bands and 5 with four bands. Add a test that every prop in `scenery.json` has a record, and that every `splits` value is in range.

### Rules for a new prop (no record yet)

Use these guesses. The owner confirmed most of them on 279 props.

1. Flat prop: one horizontal band, thickness 0.
2. Wall-mounted: one vertical band, thickness 0.
3. Name contains cloud, smoke, armor, cactus, corn or hoard: upright.
4. Name contains tree, pine, barrel, statue, rock, plant, lantern, torch, fountain, grave, sign (not on a wall), stool or similar round or organic words: upright.
5. Wide picture (width at least 1.3 times height): a horizontal top band then a vertical front band, like a cabinet.
6. Tall and thin (height at least 1.7 times width): upright.
7. Anything else: one vertical band, thickness 30% of the width (5 to 20).

The exact word list is `UPRIGHT` in the prop tuner. Copy it into the loader as a fallback only. Do not use it for props that have a record.

### Catalogue fixes (do these in `scenery.json`)

- `pine_small`: rect `[25, 15, 2, 3]` cuts the tree. Use `[27, 15, 3, 4]` on sheet `terrain`.
- `stump`: rect `[12, 12, 1, 1]` cuts the picture. Use `[12, 12, 2, 2]` on sheet `terrain`.
- `barrels_three` has a dark halo of semi-transparent pixels in the source art. Leave it. It is acceptable.

## Room shapes

The arena today is always a rectangle (`SIZES`: small 12 x 8, medium 16 x 10; `generate()` in `stage/arena.py`). Replace this with a mask of floor cells.

- **Shapes** (17): rect, long hall, L, T, cross, nave and transept, U, H, octagon, diamond, ellipse, ring, twin rooms, zigzag, dogleg, blob, cave. The code is in `iso-prototype/rooms.js` (`SHAPES`, `genRoom`). Port it to Python.
- **Size.** Pick a class: small (width 9 to 12, depth 7 to 9), medium (14 to 18 by 9 to 12), large (20 to 26 by 13 to 17). Long hall: 20 to 27 by 6 to 8. Cave: at least 13 by 10.
- **Orientation.** Apply a random one of 8 transforms (transpose, mirror x, mirror y). The seed decides. Allow a fixed orientation for tests.
- **Accept** a mask only if its largest connected part has at least `max(40, 0.3 * w * h)` cells. Keep only that part.
- **Walls and void.** Add a border of 1 cell. Any cell next to a floor cell (8 neighbours) that is not floor is a wall `#`. All other cells are outside the room. Use a new char `-` for outside. It is never drawn, never walkable, and it blocks sight like a wall. The old char `' '` already means "never seen" in `board.view`, so do not reuse it. Find every use of the arena grid characters (`WALL`, `FLOOR`, `DOOR`, `HAZARD`, and `blocked_cells`, `opaque_cells`, `reach`, `render_full` in `stage/arena.py`, plus `stage/board.py` and `stage/foes.py`) and treat `-` like a wall. `stage/crawl.py` has its own `WALL` and is not part of this plan.
- **Start zones.** `A` is the floor cell farthest from the centroid. `B` is the floor cell farthest from `A`. Fail if the distance is under 7. The party takes the cells nearest `A`. The foes take the cells nearest `B`. Prefer cells with 8 floor neighbours. This replaces the fixed west and east zones.
- **Props and features.** Place pillars and cover on cells that have all 8 neighbours as floor, are at least 3 cells from `A` and `B`, and keep a spacing above 2. Reject the room if the floor, minus props, is not one connected area. Replace the fixed column limits in `free()` and `put()` with these checks.
- **Layouts.** `chokepoint`, `pillars` and `chasm` use the rectangle centre column today. Define them on the mask instead: cut across the shorter axis through the centroid, leave a gap of 3 cells, keep both sides connected. Add tests.
- **Doors.** Today a door sits in the middle of the west and east walls. Put a door in the wall cell nearest `A` and `B`, or leave the room without doors for open scenes. A door only draws on a +x face (see "Wall block").
- **Seed.** `random.Random(f"{shape}:{seed}:{attempt}")`, at most 60 attempts. The same seed gives the same room.
- **Theme odds** (proposal, change freely): cave: cave 70%, ellipse 20%, blob 10%. Tavern or house: rect 50%, L 30%, T 20%. Temple or tomb: cross, octagon, ring, nave. Crypt: twin rooms, cross, hall. Castle: rect, twin rooms, zigzag, hall. Forest (open shell): ellipse, blob, cave, with trees on the rim and no wall blocks.
- **DM word.** Add `shape=<name>` next to `layout=` in `arena.parse`. Validate it and say the valid names in the error. Update `game/.claude/skills/stage/SKILL.md`.

## Server and data changes

- **Prop pictures.** Add `scenes.prop_atlas()`: pack every prop picture (cropped to its alpha box) into one PNG, cached by the catalogue file time. Add `GET /asset/props.png` and `GET /api/props` (rects and poses). The browser then draws any prop without one request per prop. Keep `/asset/prop/{kind}.png` until the old view is gone.
- **Arena view** (`board.view`): add `shape`. The grid may contain `-`. Keep the existing fog and walk data.
- **Room data for the scene.** Add a function that turns a scene spec into the same room data as an arena (`grid`, wall style, floor style, props with cells and faces, wall decor, stand and sit cells). The scene can use a fixed size, 10 wide and 8 deep, with the north row and the west column as walls (as in the prototype). Use `/api/scene/{location}` for it.
- **Types.** One TypeScript type `Room` for both. Combat fields (`units`, `walk`, `current`, intents) are an optional layer.
- **Actors.** No change. `/asset/actor/{id}/full.png?d=<facing>` already gives the 4 facings. A monster tile is one picture for all facings (draw it as an upright prop; scale 2 for a large one).

## Scene on the same renderer

- Scene slots become cells: zones `left, center, right` and rows `back, mid, front` map to a cell grid. In the prototype, `back_left` chests was at (2, 2), `back_right` barrels at (8, 2), `mid_center` table at (5, 4), `front_left` plant at (2, 6) and `front_right` brazier at (8, 6). Wall slots map to a position along a wall in cells. Prototype values: cabinet at 2.6, fireplace at 5.4, tapestry at 8.3 on the north wall; window at 2.6 and dresser at 5.6 on the west wall.
- `stand` and `sit` points (`scenes.stand_points`, `lib/layout.ts`) are pixel points now. Make them cells. A seated actor uses the existing sit sprite (`stage/pose.py`, hip row 48) on the seat cell.
- The mood tint (day, dusk, night, torchlit, fog, rain, snow) is a filter on the whole canvas. Keep `MOOD_FILTER` for actors and apply a matching tint to the floor layer.
- Open scenes (street, forest, camp) have no walls. Draw only floor and props.
- When this is done, `scenes.render()` and the scene PNG route have no users. Remove them in the last step.

## Work in order

Each step ends with all tests passing (`tests/run_all.py`, the TS checks in `stage/web/check`, `npm run build`). Use the pattern of `stage/web/check/layout.check.ts` for TS checks and `tests/visual_arena.py` for a picture check.

1. **Data and assets.** Fix the two catalogue rects. Load `prop_poses.json` in Python (`scenes.prop_pose(name)`). Add the atlas and the two routes. Tests: every prop has a pose, rects are valid, the atlas has every prop.
2. **Renderer library.** `stage/web/src/lib/iso.ts` (projection, picking, depth sort, wall cut rule, offscreen floor layer). `stage/web/src/lib/props.ts` (the band renderer, port of `iso-prototype/bands.js`, with the cache). TS checks: projection round trip over a grid; cut rule on an L room; a band chain on a fake picture has the expected matrices.
3. **Arena on the new renderer.** Replace the drawing in `ArenaView.tsx`. Keep every rule and control: walk range, aim preview (two taps), hover, reaction countdown, intent labels, health bars, fog (light and dim). Pick with the inverse transform. Check the phone width (the room is wider than 320 px; scale to the container). Keep the generator rectangular in this step.
4. **Shapes.** Port the shapes and the generator changes to `stage/arena.py`. Add `-` handling in board code. Add `shape=` and the theme odds. Tests: each shape gives a connected room, all starts reachable, same seed same room, the layouts still work, orientation does not change the floor count.
5. **Scene.** Build the scene room data. Draw the scene with the same renderer. Move stand and sit to cells. Remove the old scene composer and its route. Update `combat-board.md` (Return) and the stage skill.
6. **Polish.** A picture test for 5 rooms and 5 props. Check performance on a phone. Update `README.md` and the skill text.

## Open questions

None block step 1 to 3. Decide these when you reach them:

- Which face (SW or SE) each placed prop uses. The plan says a stable hash of the cell, and a wall decor item faces away from its wall. Show the owner a picture before step 6.
- The theme odds table above is a proposal.
- Doors: the plan puts a door near each start zone. The owner has not confirmed.
- Large monsters from DCSS draw upright at scale 2. A very large creature may need a footprint of more than one cell. The current board already handles sizes (`stage/data/sizes.json`). Keep the same footprints.

## Do not

- Do not change the server rules to fit the new view.
- Do not add shading settings or per-prop colour settings. Shading is fixed.
- Do not draw a made face over original art.
- Do not commit until the owner asks.
