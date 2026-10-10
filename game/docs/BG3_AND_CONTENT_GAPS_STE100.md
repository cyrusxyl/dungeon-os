# BG3 Skills and D&D Content Gaps

Date: 2026-10-09. Status: fixes 1 and 2 are built (section 8). Sections 2 to 4 show the state before the fixes.

This file is separate from `GAP_CHECKLIST_STE100.md`. That file tracks Operating Guide clauses. This file tracks D&D content.

## 1. New BG3 skills (written)
| Skill | Job |
|---|---|
| `bg3-setting` | City, gods, factions, timeline. Every fact has an era tag. |
| `bg3-cast` | Ten companions and four villains. Voice, want, secret, sheet hand-off. |
| `bg3-campaign` | Pick an era, seed `dm_story.md`, add villains and clocks, hand off. |

Rules shared by all three:
- Precedence: `canon.json` > `dm_story.md` > skill. The campaign may depart from the source.
- The skills point to `worldbuilding`, `character-creation`, `stage` and `social`. They do not copy those steps.
- BG3 house rules are opt-in. 5e stays the rules authority.
- Lore is in our own words. No wiki text is copied.

## 2. Measured content (dnd5eapi, the only rules source today)
| Data | Count | BG3 play needs |
|---|---|---|
| Races | 9 | Githyanki, drow, wood elf, half-elf variants, Zariel tiefling, goliath |
| Subraces | 4 (high elf, hill dwarf, lightfoot, rock gnome) | Many more |
| Subclasses | 12 (one per class) | At least 3 per class |
| Backgrounds | 1 (Acolyte) | Charlatan, Sage, Soldier, Folk Hero, Outlander, Noble, and more |
| Feats | 1 (Grappler) | 40 or more |
| Classes | 12 | Complete |
| Spells | 319 | Mostly complete for SRD |
| Magic items | 362 | Complete for SRD |
| Equipment | 237 | Complete for SRD |
| Conditions | 15 | Complete |
| Monsters in `dnd-cli` | `mind-flayer`, `githyanki-warrior`, `intellect-devourer` all fail. `owlbear` works. | BG3 core creatures |

Local stage data (`stage/data/`): `items.json` 6 items, `traits.json` 3 traits, `races.json` 11 looks (no githyanki, no wood elf), `class_looks.json` 12 classes, `monsters.json` 121, `presets.json` 23.

## 3. Gaps by layer
Rank: B = blocks BG3 companions or campaign. N = nice to have.

| ID | Layer | Gap | Rank |
|---|---|---|---|
| R1 | Rules data | `character new` calls `races/<name>` and `subraces/<name>` and stops with an error if missing. Githyanki, drow, wood elf and half-elf subraces fail. Backgrounds have a fallback (`--background-skills`). Races have none. The "BG3 epilogue" path in `character-creation` therefore breaks for Lae'zel, Halsin, Minthara and Shadowheart. | B |
| R2 | Rules data | Only 1 background. Only 1 feat. | B |
| R3 | Rules data | One subclass per class. Companions need Trickery, Fiend (have), Battle Master, Moon, Vengeance and more. | B |
| M1 | Rules data | Mind flayer, intellect devourer, githyanki and similar monsters are not in the SRD. No API will supply them. | B |
| E1 | Engine | `level-up` has no feat path beyond `none` (the sheet uses `none` for a feat). Feats give no effect. | N |
| E2 | Engine | No multiclass support was checked. Open multiclassing is a BG3 rule. | N |
| S1 | Stage data | `items.json` (6) and `traits.json` (3) cover few effects. Magic items and class feature rules are text only. | N |
| L1 | Looks | `races.json` has no githyanki, wood elf or Zariel tiefling look. | N |
| X1 | Content | Larian-only spells, items and Illithid powers do not exist in any open source. | N |

## 4. Fixes, cheapest first
1. **Local override folder** (closes R1, R2, R3, M1). Add `game/data/overrides/<endpoint>.json`. Make `api_get` read it before the network. Hand-write races, subraces, backgrounds, subclasses and monsters in the same JSON shape as the API. One fetch path serves all. The cache keeps working. Cost: one small function, plus data entry.
2. **Open5e `srd-2024`** (helps R2). Live check: 4 backgrounds (Acolyte, Criminal, Sage, Soldier), 17 feats, 9 species (adds Goliath and Orc), 24 class entries. It is open data. The endpoint is `api.open5e.com/v2/` with `document__key=srd-2024`. Open question below.
3. **Open5e `srd-2014`**: adds nothing (1 background). Skip.
4. **Third-party documents on Open5e** (a5e, Kobold Press, Tal'dorei): 58 backgrounds and 91 feats exist. Their flavor does not match Baldur's Gate. Use only to copy shape, not content.
5. **Engine work after data** (E1, E2, S1): feats with effects, multiclass, more item rules. Do this only when a table needs it (YAGNI).
6. **Looks** (L1): add githyanki, wood elf and Zariel tiefling entries to `races.json` using existing LPC parts.

## 5. Open questions (answered by the host on 2026-10-09)
- **2014 or 2024 rules?** Answer: a 2024 background increase **replaces** the race increase. The code does this (`--background-bonus`).
- **BG3 flexible +2/+1 bonus?** If yes, it replaces racial bonuses. Opt-in only.
- **Which era is the next BG3 campaign?** See `bg3-campaign`.
- **Must companion sheets be exact?** If not, use the closest SRD race now and wait for fix 1.

## 6. Unverified items
- Free smites: the BG3 wiki pages that we read did not list them. Treat as unconfirmed.
- Companion secrets for Lae'zel, Halsin, Jaheira and Minsc: the wiki states none. Entries are DM advice.
- The multiclass check in E2 was not done in code.

## 7. Sources
BG3 wiki pages for each companion and for the D&D 5e rule changes. Open5e v2 API (live counts). dnd5eapi (live counts).

## 8. What was built (fixes 1 and 2)
Code:
- `dnd_cli/sources.py`: one layer that `api_get` and `api_list` call. It reads hand-written overrides first, then Open5e `srd-2024`.
- `dnd_cli/data/overrides/<resource>/<index>.json`: 30 hand-written files in the dnd5eapi shape. A file with `_extend` adds list entries (for example new subraces on `races/elf`).
- `dnd_cli/creation.py`: a 2024 background gives its ability increase, replaces the race bonus, and adds its origin feat. A subrace can set speed.
- `character new --background-bonus`, and a +2/+1 picker in the web creator (`CharacterCreator.tsx`). `npm run build` passes. The picker was not tested in a browser.
- Read order: a full-replace override is read before the network. Misses from dnd5eapi fall back to Open5e. `search monsters` also reads overrides.
- Stage looks: `intellect-devourer` uses the `brain_worm` tile, `githyanki-warrior` has a preset. `mind-flayer` already had a tile.
- Tests: `tests/test_sources.py`, and new checks in `tests/test_creation.py`. All 14 suites pass.

Content now present:
| Kind | Added |
|---|---|
| Backgrounds (Open5e) | Criminal, Sage, Soldier |
| Feats (Open5e) | 16 more (17 total with Grappler) |
| Backgrounds (override) | Charlatan, Folk Hero, Outlander, Noble |
| Races (override) | Githyanki; subraces Drow and Wood Elf |
| Subclasses (override) | Trickery Domain, Battle Master, Circle of the Moon, Oath of Vengeance, Arcane Trickster |
| Monsters (override) | Mind Flayer, Intellect Devourer, Githyanki Warrior |

Test: Lae'zel, Minthara, Halsin and Astarion built live on a temporary copy of the example campaign. A fight with the three new monsters started, and Mind Blast shows as a recharge ability.

## 9. Still open
- Open5e goliath and orc species are not converted. Their shape differs. Add only if a table asks.
- Zariel tiefling (Karlach) has no subrace data. Use `--race tiefling` now (R4).
- Subclasses are reference text. `level-up` does not apply their features (E1).
- Feats have no mechanical effect on the sheet beyond a name and a one-line text (E1).
- Looks for githyanki and wood elf (L1). `actor set` falls back to a human look.
- A drow pick in the creator keeps the elf look. `look_race` is per race, not per subrace.
- Intellect Devourer: Devour Intellect (2d10 psychic, then 3d6 against Intelligence) matches public sources. Its resistances and condition immunities are NOT in the file, because no source confirmed them. Add them when you check your book.
- Hand-written monster and race numbers are from memory of the 5e books. Check them against your own copy. The repo is public. The monster and race text is rewritten in our own words, and only the numbers are kept. Names such as Githyanki and Mind Flayer are WotC product identity: remove those files if you want a fully open repo.

## 10. Review round 2 (2026-10-10)
- Added server tests: a Sage character with `background_bonus` as a list, and a Sage with no bonus (400, nothing written).
- A converted Open5e record is now cached under its own endpoint. This removes the failed dnd5eapi call on each read and lets `search feats` work after `warmup feats`.
- Added a test that a replacing override is read with the network off.
- Monster text rewritten in our own words (the repo is public).
- Lore fix: Wyrm's Rock is a fortress on an islet at Wyrm's Crossing. Rivington is the camp across the river. Added both.
- `cache_warmup.py` builds endpoints from `index`, so list entries with override or Open5e urls are safe.
