# Maps and Dungeon Crawl

Design for travel and exploration on the visual stage. The stage has three levels:

| Level | Example | How the party moves | Who decides |
|---|---|---|---|
| Region map | Sword Coast | Click a known place, confirm, the DM tells the trip | DM |
| City map | Baldur's Gate | Same as region | DM |
| Site | Sunless Citadel, a manor | Walk tile by tile in a generated map | The stage; the DM only for events |

Rules that apply to all levels:

- **The DM reveals.** A place or a point of interest (POI) is on the map only after the DM adds it, or after the party sees it while exploring.
- **Looking is free.** Opening the map, changing level, and walking in a site use no DM tokens. Only these actions call the DM: Travel (after a confirm), Examine, Leave, a POI seen for the first time, and a wandering-encounter hit.
- **Hidden stays hidden.** The browser gets only what the party knows. The server never sends an unseen cell, an unfound POI, or a hidden place. A prompt to the DM never names them either: the console drawer shows those prompts.
- **The DM gives no positions.** It gives directions (`dir=n`) and depths (`@far`). The stage computes the layout.

## 1. Region and city maps

### Data

`{campaign}/stage/maps/<map-id>.json`:

```json
{
  "name": "Sword Coast",
  "places": {
    "baldurs-gate": {"name": "Baldur's Gate", "icon": "city", "at": [0, 0], "known": true, "visited": true},
    "candlekeep":   {"name": "Candlekeep", "icon": "tower", "at": [0, -2], "known": true, "visited": false}
  },
  "routes": [{"a": "baldurs-gate", "b": "candlekeep", "travel": "2 days"}]
}
```

- **Known routes.** A route shows when the players know both of its places.

- **Nesting.** A map with `"in": "sword-coast"` is the inside of the place with the same id in `sword-coast`. The city map `baldurs-gate` is the inside of the place `baldurs-gate`. A site is the inside of the place with the same id as the site.
- **Unique ids.** A place id is unique in the campaign. It is also the location id of the scene (`@scene chapel-of-ilmater`).

### DM commands

One command per Bash call:

```bash
uv run dnd-cli map place sword-coast baldurs-gate "name=Baldur's Gate" icon=city
uv run dnd-cli map place sword-coast candlekeep icon=tower from=baldurs-gate dir=n travel=2_days
uv run dnd-cli map place baldurs-gate chapel-of-ilmater in=sword-coast icon=temple from=elfsong-tavern dir=s travel=15_min
uv run dnd-cli map route sword-coast candlekeep beregost travel=3_days
uv run dnd-cli map reveal sword-coast cloakwood
uv run dnd-cli map show sword-coast
```

- `place` creates the map if it does not exist. The first place of a map is at its center. A later place needs `from=` and `dir=`, and it gets a route from that place.
- `dir=` is `n`, `ne`, `e`, `se`, `s`, `sw`, `w` or `nw`. The layout steps in that direction until it finds a free spot.
- `hidden=yes` adds a place that the players do not know yet. `reveal` shows it later, with its routes to known places.
- `icon=` comes from a fixed list (`uv run dnd-cli map options`). Without it, the stage guesses from the id.

### Party position

`dnd-cli show beat` checks each `@scene <id>` and `@explore <id>`. If the id is a place on a map, it appends an `at` event, and it marks the place known and visited. A scene that is not a place (a road scene for an ambush, a room inside a building) leaves the position where it was.

### Player view

- The **Map** button opens an overlay. It shows the current level: the site (when the party explores one) or the map that holds the current place. An **Up** button shows the level above. A **Back** button returns to the current level.
- On a graph map, the overlay shows known places with icons, known routes with travel times, and the party marker. A place that was not visited is dim.
- Clicking a known place asks "Travel to Candlekeep?". On confirm, the server finds the shortest known route and sends this prompt to the DM:

  ```
  [map] The party travels from Baldur's Gate to Candlekeep: Baldur's Gate → Candlekeep (2 days). Run the journey (encounter checks on the way), then show the arrival with `@scene candlekeep`.
  ```

  With no known route, the prompt says "no known route; the party goes across country".

## 2. Sites: buildings and dungeons

A site is one floor, generated from a seed and saved. The party walks in it. The DM sets the site and its POIs; the stage does the walking, the fog, and the checks. In the site view, the DM does not describe the layout or give movement choices: the players see the map.

### DM commands

```bash
uv run dnd-cli site set sunless-citadel name=Sunless_Citadel theme=crypt size=medium danger=low poi=dragon-altar@far poi=goblin-camp@mid:goblin poi=old-well@near:fountain
uv run dnd-cli site set sunless-citadel --change danger=mid poi=hidden-cache@any:chest
uv run dnd-cli site show sunless-citadel
uv run dnd-cli site preview sunless-citadel
```

- `theme=` sets the tiles and the generator: `dungeon`, `crypt`, `cave`, `sewer`, `temple`, `castle`, `house`, `tavern`, `manor`.
- `size=` is `small`, `medium` or `large`.
- `danger=` is the wandering-encounter chance when the party enters an area for the first time: `none`, `low` (1 in 8), `mid` (1 in 5), `high` (1 in 3). The default is `low` for dungeon themes and `none` for building themes.
- `poi=<id>@<where>[:<icon>]` places a point of interest.
  - `where` is `entrance`, `near`, `mid`, `far` or `any`, counted by walking distance from the entrance.
  - `icon` is a fixed object (`altar`, `chest`, `stairs-down`, `statue`, ...) or an actor kind (`goblin`, `skeleton`, a saved actor id). An actor shows as its sprite.
- A saved site is final. `--change` can change `name=` and `danger=` and add POIs. New POIs go to areas the party has not seen. The layout never changes; a new layout needs a new site id.
- More floors are more sites. A POI `stairs-down` on floor 1 leads to the site of floor 2 (see `@explore`).

### Beat line

| Line | Effect |
|---|---|
| `@explore <site-id>` | Show the site. The party stands where it stood last, or at the entrance on the first visit. |
| `@explore <site-id> <poi-id>` | Show the site with the party at that POI (for stairs between floors). |
| `@explore <site-id> entrance` | Show the site with the party at the entrance. |

`@scene` leaves the site view. The DM uses it for a close scene (combat with actors, a talk), then sends `@explore <site-id>` to go back to walking.

### Data

`{campaign}/stage/sites/<site-id>.json`. It holds the full layout, so it is secret: the server sends the browser only the seen part.

```json
{
  "spec": {"name": "Sunless Citadel", "theme": "crypt", "size": "medium", "seed": 81723, "danger": "low"},
  "grid": ["##########", "#....+...#", "..."],
  "areas": [{"x": 3, "y": 4, "w": 6, "h": 5, "cx": 6, "cy": 6, "depth": 0}],
  "area_of": ["....", "..."],
  "entrance": [6, 6],
  "pois": {"dragon-altar": {"x": 30, "y": 9, "where": "far", "icon": "altar", "found": false}},
  "party": [6, 6],
  "seen": ["0000111100", "..."],
  "entered": [0]
}
```

Grid cells: `#` wall, `.` floor, `+` closed door, `'` open door, `<` entrance and exit.

### Generator

Plain Python, seeded, no libraries:

- **rooms** (dungeon, crypt, sewer, temple, castle): binary space partition (BSP). Each leaf gets a room with a margin. Sibling subtrees join with an L-shaped corridor. A corridor cell on a room's edge, with wall on both sides, becomes a door.
- **building** (house, tavern, manor): BSP with no margin. Rooms share walls, and sibling subtrees join with one door in the shared wall. The outer wall gets the entrance.
- **cave** (cave): cellular automaton (45% fill, 5 steps of the 4-5 rule). The stage keeps the largest region and fills the rest. Areas are grown from spread-out seed cells (a multi-source flood fill), because a cave has no rooms.

Every style gives **areas** (rooms, or cave regions). The entrance is in the area nearest to the bottom edge. The depth of an area is its walking distance from the entrance. A POI goes to an unused area of the right depth band (`near` the first third, `mid` the middle third, `far` the last third). It is placed near the area center, never on a wall or a door.

Invariants (tested over many seeds): every floor cell and every POI can be reached from the entrance, and the same seed gives the same grid.

### Sight

- The radius is 8 tiles. The stage traces a Bresenham line from the party to each cell on the edge of the radius square, and stops each line at the first wall or closed door. A cell outside the circle is not seen.
- After the rays, a wall or door cell next to a seen floor cell is also seen. Without this pass, room corners stay black.
- In a doorway or on the entrance (a gap in a wall line), the party also sees what the floor cells next to it see. Without this, every line along the inside of the wall is cut.
- A cell is **seen** once and stays on the map. A cell is **visible** while it is in sight now. The view draws visible cells bright, seen cells dark, and other cells black.

### Walking

- Arrow keys and WASD move one tile. A click on a seen cell walks the shortest path over seen cells. A click on a found POI walks next to it, and not below it (the party sprite would hide it). The keys do nothing while the focus is in a text field, a button or the console.
- Walking into a closed door opens it and steps into it.
- The server does each step, and stops the walk when one of these happens:
  - **A POI is seen for the first time.** The server marks it found and sends: `[explore] Sunless Citadel: the party sees Dragon Altar (dragon-altar). Show what they find. Do not describe exits or passages: the players see the map and walk by themselves. If you switch to an @scene, send @explore sunless-citadel when it is over.`
  - **First entry into an area, and the wandering check hits.** The server rolls in secret and sends: `[explore] Sunless Citadel: a wandering encounter check hit (danger low). Run a wandering encounter, or show that nothing comes.` and the same last two sentences.
- **Examine.** On or next to a found POI, an Examine button sends: `[explore] Sunless Citadel: the party examines Dragon Altar (dragon-altar). ...`
- **Leave.** On the entrance, a Leave button sends: `[explore] Sunless Citadel: the party leaves by the entrance. Show where they go next.`
- The server refuses a move when the DM is not idle, and from the moment it sends a prompt until the DM takes it. The browser also waits until the player has read the dialogue.
- The party position and the seen cells are saved after each walk.

### Look

- Tiles are 32 px top-down DCSS tiles (CC0, already fetched for monster tiles). Each theme names its wall, floor, door and exit tiles in `stage/data/crawl.json`.
- The party marker is the lead character's LPC sprite, facing the way it walks: the first of `party_members` in state.json, else the first character file. A POI shows as its object tile or its actor sprite. Sprites are drawn in depth order.
- The view is a 15 × 9 tile window that follows the party, scaled by an integer factor.
- In the Map overlay, the site shows as a small flat-color map of the seen cells, with the found POIs and the party.

## 3. Server API

| Route | Use |
|---|---|
| `GET /api/map` | The levels from the current one up: site (if exploring), then the maps. |
| `GET /api/map/{id}` | Known places and routes of one map, and the party's place in it. |
| `POST /api/map/travel` | `{map, to}`: sends the travel prompt. |
| `GET /api/site/{id}` | The seen part of a site, visible cells, found POIs, party, tile info. |
| `POST /api/site/{id}/move` | `{dir}` or `{to: [x, y]}`: walks, returns the new view, the path, and why it stopped. |
| `POST /api/site/{id}/act` | `{kind: "examine", poi}` or `{kind: "leave"}`: sends the prompt. |
| `GET /asset/crawl/{theme}.png` | The tile atlas of a theme. |
| `GET /asset/icon/{name}.png` | A map or POI icon. |

Stage events: `explore {site, at?}`, `at {map, place}`, `map_updated {map}`, `site_updated {site}`. The state gets `explore` (the site id, or null) and `place` (`{map, place}`).

## 4. Not in this version

- A second browser tab does not follow the walk live. It catches up on the next event.
- No removal of a POI. A found POI stays on the map.
- No combat grid. Combat is a scene, as before.
- The region map is a schematic with icons, not a painted map.
