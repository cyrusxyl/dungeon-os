# DungeonOS Gap Checklist
## Written in Simplified Technical English (ASD-STE100 style)

**Purpose:** This file checks the DungeonOS codebase against every clause in `DM_Campaign_Checklist_STE100.md` (CL) and `AI_DM_Operating_Guide_STE100.md` (OG), both in this same folder (`game/docs/`). It records what exists, what was added, and what still needs a human decision.

**Location:** This file lives at `game/docs/GAP_CHECKLIST_STE100.md`, next to the two documents it checks — not at the repository root — because every row in it cites a file under `game/`. `game/AGENTS.md` links to all three documents under "Source documents."

**Date of this check:** 2026-08-11. Updated same day after adding the `dnd-cli canon` tool (see "What is verified" at the end).

**Status codes:**
- `DONE` — implemented and confirmed present in the repo.
- `DONE, code-enforced` — implemented as code, not prose, and the code was run against test cases (not just read). See "What is verified" at the end.
- `DONE, untested` — implemented as instruction text only. Its *behavior* under pressure has not been run in a live session.
- `PARTIAL` — some support exists, but not the full clause.
- `N/A` — the clause does not apply here. A reason is given.
- `OPEN` — the code cannot resolve this. It needs an answer from the user or the players.

---

## Part 1: DM Campaign Checklist (CL)

### Section 1 — Before You Write the Story

| Clause | Requirement | Status | Where |
|---|---|---|---|
| CL-1.1 | Premise in one sentence | DONE | `worldbuilding` skill, Story Bible item 1 |
| CL-1.2 | One session-1 hook | DONE | `worldbuilding` skill, Story Bible item 1 (added) |
| CL-1.3 | Set the tone | DONE | `config.schema.json` `tone` field |
| CL-1.4 | 6-10 sessions for a first campaign | DONE | `config.schema.json` `planned_length_sessions` |
| CL-1.5 | 3-5 world truths | DONE | `worldbuilding` skill, Story Bible item 2 (added) |
| CL-1.6 | Do not write full world history | PARTIAL | Story Bible item 2 says "write only what session 1 needs." No hard enforcement — depends on the DM's judgment each time. |
| CL-1.7 | One starting location, 2-3 details | DONE | `location.schema.json`, `notable_features` |

### Section 2 — Design the Villains

| Clause | Requirement | Status | Where |
|---|---|---|---|
| CL-2.1 | 1 to 3 villains | DONE | `worldbuilding` skill, Story Bible item 6 |
| CL-2.2 | One clear goal per villain | DONE, code-enforced | `canon.schema.json` `villains[].goal` (required); `dnd-cli canon add-villain` cannot be called without one |
| CL-2.3 | Three actions toward the goal | DONE, code-enforced | Read as "three quests" — `dnd-cli canon add-clock` (one call per quest), each clock's `segments_total` restricted to 4/6/8 at the argparse level |
| CL-2.4 | A way to escape capture | DONE (field) / OPEN (answer) | `canon.schema.json` has an optional `villains[].escape_plan` field, settable with `add-villain --escape-plan`. No villain in `baldurs-gate/canon.json` has one filled in yet — `dm_story.md` gives weaknesses (pressure points), not escape plans, and the two are not the same thing. Needs a DM decision, not a guess. |
| CL-2.5 | One clear trait | DONE, code-enforced | `canon.schema.json` `villains[].trait` (required); `add-villain` cannot be called without one |
| CL-2.6 | Villain acts even off-screen | DONE | Replaced by clock rules. See OG-2.9 and `dm-canon-procedures` skill. This is OG Correction 14.5. |

### Section 3 — Design the Story Structure

| Clause | Requirement | Status | Where |
|---|---|---|---|
| CL-3.1 | Situations, not a fixed plot | PARTIAL | The Story Branches structure supports this. No file forces a DM to think in "situations." |
| CL-3.2 | A situation has a location, a person, a goal | PARTIAL/OPEN | Not a required structure anywhere. Left to the DM's judgment during play. |
| CL-3.3 | Three-clue rule | DONE | `dm-craft-principles` skill |
| CL-3.4 | Place a clue in more than one location | DONE | `dm-craft-principles` skill |
| CL-3.5 | If all clues are missed, move the story forward anyway | DONE | `dm-craft-principles` skill, plus thread staleness-3 rule (OG-3.5) |
| CL-3.6 | Let player choices change the story | DONE | Story Branches structure in `dm_story.md` |
| CL-3.7 | Clear end point, not a fixed path | DONE | Each Story Branch states an endpoint |
| CL-3.8 | End on a cliffhanger when possible | DONE | `dm-craft-principles` skill |

### Section 4 — Balance the Three Types of Play

| Clause | Requirement | Status | Where |
|---|---|---|---|
| CL-4.1 | Combat, exploration, social defined | DONE | Three matching skills exist |
| CL-4.2 | Do not use only one type across the campaign | DONE | `dm-craft-principles`, Common Mistakes |
| CL-4.3 | At least one combat chance per session | OPEN | Judgment call during live play. Not mechanically enforced. |
| CL-4.4 | At least one exploration chance per session | OPEN | Same as above. |
| CL-4.5 | At least one social chance per session | OPEN | Same as above. |
| CL-4.6 | Adjust balance to player taste | DONE | `dm-craft-principles`, "After Each Session" |

### Section 5 — Use Player Backstories

| Clause | Requirement | Status | Where |
|---|---|---|---|
| CL-5.1 | Ask about backstory people/places | DONE | `character-creation` skill (added) |
| CL-5.2 | Ask about an unfinished problem | DONE | `character-creation` skill (added) |
| CL-5.3 | Add backstory people/places to the campaign | DONE | `worldbuilding` skill, Player-Specific Hooks |
| CL-5.4 | Do not remove player control; do not kill a backstory person without permission | DONE | `dm-craft-principles`, "Respect and Backstories" (added) |
| CL-5.5 | Equal backstory time per player | DONE | Covered by the spotlight-rotation rule |
| CL-5.6 | Backstory creates a new problem, not an ending | DONE | `dm-craft-principles`, "Respect and Backstories" (added) |

### Section 6 — Run Session Zero

| Clause | Requirement | Status | Where |
|---|---|---|---|
| CL-6.1 | Hold a Session Zero meeting | OPEN | Cannot be done by the code. This is a real conversation with the player. |
| CL-6.2 | State tone, genre, length | DONE (field) / OPEN (answer) | `config.schema.json` holds the field. `baldurs-gate/config.json` has tone and length filled in already. |
| CL-6.3 | State rules and source books | DONE | `config.json` `source_books_allowed`, filled with the SRD 5.1 default already in use |
| CL-6.4 | Ask about character death handling | DONE (field) / OPEN (answer) | `config.schema.json` `character_death_policy`. Not yet answered for `baldurs-gate`. |
| CL-6.5 | Ask about hard limits and soft limits | DONE (field) / OPEN (answer) | `config.schema.json` `safety_limits`. Not yet answered for `baldurs-gate`. |
| CL-6.6 | Agree on table rules | N/A | `baldurs-gate` is a solo, asynchronous campaign. No shared table, phones, or side talk to manage. |
| CL-6.7 | Agree on the schedule | OPEN | `config.schema.json` `table_rules` holds the field; not yet answered. |
| CL-6.8 | Decide how PCs know each other | N/A | `baldurs-gate` has one player character (Sireth). There is no party to introduce. |
| CL-6.9 | Write down and keep the agreements | DONE | `config.json` is that written record, once the OPEN items above are answered |

### Section 7 — Prepare Each Session

| Clause | Requirement | Status | Where |
|---|---|---|---|
| CL-7.1 | Review each character, find a hook | PARTIAL | `AGENTS.md` Session Start reads character files, but does not force a hook-finding step |
| CL-7.2 | Strong start in the first five minutes | N/A | Written for a human prepping on paper before a session. The AI DM improvises the opening from `state.json` and the recap; there is no offline prep step to check this against. |
| CL-7.3 | Bullet-point scene list, not full scenes | N/A | Same reason as CL-7.2 — the AI DM generates content live via the `worldbuilding` skill instead of pre-writing scenes. |
| CL-7.4 | About ten loose clues, not tied to one location | N/A | Same reason. Live generation replaces pre-writing. |
| CL-7.5 | One sentence + details per location | DONE | `location.schema.json` |
| CL-7.6 | Name + one trait per minor NPC | DONE | `worldbuilding` skill, Quick NPC section |
| CL-7.7 | Loose monster list | N/A | Replaced by live `dnd-cli`/API lookups — see `AGENTS.md` Section 2 |
| CL-7.8 | Magic item rewards, some matched to characters | PARTIAL | `canon.schema.json` Part E records items given, but nothing prompts the DM to prepare matched rewards in advance |
| CL-7.9 | Do not prepare unused content | DONE | Matches "load skills only when needed" and live-generation philosophy already in `AGENTS.md` |

### Section 8 — Run the Game: General Rules

| Clause | Requirement | Status | Where |
|---|---|---|---|
| CL-8.1 | Main duty is to help players have fun | DONE | `dm-craft-principles`, "Respect and Backstories" (added) |
| CL-8.2 | Shared story, not a competition | DONE | Same as above |
| CL-8.3 | Be fair, same rules for everyone | DONE | `AGENTS.md`, Player Permissions |
| CL-8.4 | Stay flexible | DONE (corrected) | OG Correction 14.1, in `AGENTS.md` Canon rule 1: flexible about the path, not about a canon fact |
| CL-8.5 | Talk to players about problems before they build up | N/A | Solo, asynchronous campaign — no ongoing inter-player friction to manage. Would apply if a second player joins. |
| CL-8.6 | Correct mistakes and continue | DONE (corrected) | OG Correction 14.4, in `AGENTS.md` Error Handling |

### Section 9 — Decide When to Roll Dice

| Clause | Requirement | Status | Where |
|---|---|---|---|
| CL-9.1 | Roll only if success and failure are both possible | DONE | `dm-craft-principles`, "When to Call for a Dice Roll" |
| CL-9.2 | Roll only if failure has a real result | DONE | Same section |
| CL-9.3 | Do not roll for an easy task | DONE | Same section |
| CL-9.4 | Do not roll for an impossible task | DONE | Same section |
| CL-9.5 | Success at a cost after a failed roll | DONE | Same section |

### Section 10 — Run Combat Well

| Clause | Requirement | Status | Where |
|---|---|---|---|
| CL-10.1 | A real choice every turn | DONE | `dm-craft-principles`, "Combat Pacing" |
| CL-10.2 | End combat once real choices run out | DONE | Same section |
| CL-10.3 | Interactive terrain | DONE | Same section |
| CL-10.4 | Warn about a dangerous threat first | DONE | Same section |
| CL-10.5 | Describe the result only after the roll | DONE | Same section |
| CL-10.6 | Prepare monster stat blocks in advance | N/A, adapted | Replaced by live `dnd-cli` lookups (`AGENTS.md`, `combat` skill) — same goal (fast, accurate combat), different method for an AI DM |

### Section 11 — Manage Session Pacing

| Clause | Requirement | Status | Where |
|---|---|---|---|
| CL-11.1 | Watch for boredom | DONE | `dm-craft-principles`, "Session and Table Pacing" |
| CL-11.2 | Ask a quiet player a direct question | DONE | Same section |
| CL-11.3 | Add an event if planning stalls | DONE | Same section |
| CL-11.4 | Move the spotlight often | DONE | Same section |
| CL-11.5 | Keep scenes short | DONE | Same section |

### Section 12 — Manage the Table

| Clause | Requirement | Status | Where |
|---|---|---|---|
| CL-12.1 | Spotlight time for each player | DONE | Covered by CL-11.4 |
| CL-12.2 | Talk to a disruptive player outside the session | N/A | Solo campaign, text medium. No "outside the session" channel exists in this system. |
| CL-12.3 | Talk to a player who takes DM choices personally, outside the game | N/A | Same reason |
| CL-12.4 | Treat all players with respect; do not mock a choice | DONE | `dm-craft-principles`, "Respect and Backstories" (added) |

### Section 13 — Use Improvisation

| Clause | Requirement | Status | Where |
|---|---|---|---|
| CL-13.1 | Say "yes" when you can | DONE (corrected) | OG Correction 14.2, in `AGENTS.md` Canon rule 8 and `dm-craft-principles`: yes at the free level only |
| CL-13.2 | Do not say "no" without a clear reason | DONE | `dm-craft-principles`, "Improvisation" |
| CL-13.3 | Prefer "yes, but" / "no, and" over a flat no | DONE | Same section |
| CL-13.4 | Write down invented names and details for later use | DONE | Canon-level improv rule — `AGENTS.md` Canon rule 8, `canon.json` Part C |

### Section 14 — Give Meaningful Consequences

| Clause | Requirement | Status | Where |
|---|---|---|---|
| CL-14.1 | Every failed roll has a real consequence | DONE | `dm-craft-principles`, "Meaningful Consequences" |
| CL-14.2 | Consequence comes from the character's action | DONE | Same section |
| CL-14.3 | Avoid consequences with no purpose | DONE | Same section |
| CL-14.4 | Show the result of an earlier choice later | DONE | Same section |

### Section 15 — Common Mistakes

| Clause | Requirement | Status | Where |
|---|---|---|---|
| CL-15.1 | Do not railroad | DONE | `dm-craft-principles`, "Common Mistakes" |
| CL-15.2 | Do not over-prepare | DONE | Matches "load skills only when needed" philosophy |
| CL-15.3 | Do not allow metagaming | DONE | `dm-craft-principles`, "Common Mistakes" |
| CL-15.4 | Do not use only one play type | DONE | Same section (also CL-4.2) |
| CL-15.5 | Do not call a roll with no stakes | DONE | Same section (also CL-9.2) |
| CL-15.6 | Do not let one player dominate | DONE | Same section (also CL-11.4) |
| CL-15.7 | Do not kill a recurring villain too early | DONE | Same section (also CL-2.4) |
| CL-15.8 | Do not compare your table to a professional stream | DONE | `dm-craft-principles`, "Respect and Backstories" (added) |

### Section 16 — After Each Session

| Clause | Requirement | Status | Where |
|---|---|---|---|
| CL-16.1 | Write a short recap | DONE | `dm-craft-principles`, "After Each Session"; feeds `session_log.md` |
| CL-16.2 | Read the recap at the start of next session | DONE | `AGENTS.md`, Session Start step 6 |
| CL-16.3 | Ask players for feedback | DONE | `dm-craft-principles`, "After Each Session" |
| CL-16.4 | Adjust prepared material to player interest | DONE (corrected) | OG Correction 14.3, in `AGENTS.md` Canon rule 6 and `dm-craft-principles`: adjust scenes, not clocks |

---

## Part 2: AI DM Operating Guide (OG)

This guide has priority over the Checklist. Its rules had **no prior implementation** anywhere in the repo before this check — the entire canon-file system below is new.

### Section 1 — The Canon File

| Clause | Requirement | Status | Where |
|---|---|---|---|
| OG-1.1 | Keep a canon file | DONE | `{campaign}/canon.json`, `game/schemas/canon.schema.json` |
| OG-1.2 | Keep it outside the conversation | DONE | It is a file on disk, read fresh each time |
| OG-1.3 | If a fact is not in the canon file, it is not true | DONE | `AGENTS.md`, Canon rule 1 |
| OG-1.4 | Do not use conversation history as a fact record | DONE | Same rule |
| OG-1.5 | Read the canon file at session start | DONE | `AGENTS.md`, Session Start step 5 |
| OG-1.6 | Write to it at session end | DONE | `AGENTS.md`, Session End; procedure in `dm-canon-procedures` |
| OG-1.7 | Seven parts, A through G | DONE | `canon.schema.json`: `villains`, `threads`, `facts`, `characters`, `items`, `promises`, `rulings` |

### Section 2 — Villain Clocks

| Clause | Requirement | Status | Where |
|---|---|---|---|
| OG-2.1 | Three quests per villain | DONE | `canon.schema.json` `villains[].clocks`; created with `dnd-cli canon add-clock` |
| OG-2.2 | Clock has 4, 6, or 8 segments | DONE, code-enforced | `canon.schema.json` enum, and `dnd-cli canon add-clock` rejects any other value at the argparse level — a bad value never reaches the file. Tested: `add-clock ... 5` fails with `invalid choice: '5' (choose from 4, 6, 8)`. |
| OG-2.3 | Record each clock in Part A | DONE | `canon.json` `villains[].clocks` |
| OG-2.4 | Advance by one segment at session end, by default | DONE, code-enforced | `dnd_cli/canon.py:advance_clock`, run via `dnd-cli canon advance-clock`. Tested on a scratch campaign: 0 to 1. The LLM never computes the new number. |
| OG-2.5 | Do not advance if players took direct action | DONE, code-enforced | Same function, `--action-taken` flag. Tested: value held at 3 across a call with the flag set. |
| OG-2.6 | Advance by two if players ignored a clear warning | DONE, code-enforced | Same function, `--warning-ignored` flag. Tested: 1 to 3. |
| OG-2.7 | Full clock completes the villain's quest | DONE, code-enforced | Same function sets `status: "complete"` when `segments_filled` reaches `segments_total`, and a further `advance-clock` call on that clock is refused. Tested on a scratch campaign: 3 to 4, status flips, next call errors "already complete." |
| OG-2.8 | Tell players the result of a full clock | DONE, untested | The code reports `status: "complete"` in its output; whether the AI DM actually narrates the consequence to the players next session is a live-session behavior claim, not something the code can enforce. |
| OG-2.9 | Advance clocks only by these rules, not by feel | DONE, code-enforced | `advance_clock` has exactly three branches (2.4, 2.5, 2.6) and no fourth path. There is no argument that lets the caller set an arbitrary segment count. |

### Section 3 — The Thread Ledger

| Clause | Requirement | Status | Where |
|---|---|---|---|
| OG-3.1 | Record open threads in Part B | DONE | `canon.json` `threads` |
| OG-3.2 | Track staleness count per thread | DONE | `canon.schema.json` `threads[].staleness_count` |
| OG-3.3 | Increase staleness if the thread did not appear | DONE, code-enforced | `dnd_cli/canon.py:sweep_threads`, run via `dnd-cli canon sweep-threads --appeared ...`. Tested: a thread left out of `--appeared` went 0 to 1 to 2 to 3 across three sweeps. |
| OG-3.4 | At staleness 2, put the thread back into play | DONE, code-enforced (alert) / DONE, untested (compliance) | `sweep_threads` returns `alert: "put back into play..."` exactly when `staleness_count == 2` — tested. Whether the AI DM actually brings the thread back next session on seeing that alert is a live-session behavior claim. |
| OG-3.5 | At staleness 3, the world acts on it regardless | DONE, code-enforced (alert) / DONE, untested (compliance) | Same function returns `alert: "world acts now..."` at `staleness_count >= 3` — tested. Acting on the alert is still a live-session behavior claim. |
| OG-3.6 | Reset staleness to 0 when the thread appears | DONE, code-enforced | Tested: a thread id passed in `--appeared` reset from 2 to 0 in the same call that advanced other threads. |
| OG-3.7 | No more than five open threads | DONE, code-enforced | Two layers, both tested: `canon.schema.json` `maxItems: 5` (structural), and `dnd-cli canon add-thread` itself refuses a sixth thread before it ever reaches the file — confirmed with `Error: Already at the five-thread cap`. |
| OG-3.8 | Close or merge a thread before opening a sixth | DONE, code-enforced | `add-thread`'s refusal message names `close-thread` as the required next step; `close-thread` was tested and removes a thread by id, erroring clearly on an unknown id. |

### Section 4 — The Arc-Touch Gate

| Clause | Requirement | Status | Where |
|---|---|---|---|
| OG-4.1 | At least one scene touches a villain clock per session | DONE, untested | Deciding *which scene* qualifies is a judgment call the code cannot make. `dnd-cli canon touch-clock` records the decision once the DM has made it. |
| OG-4.2 | Do not end a session before this happens | DONE, code-enforced | `dnd-cli canon close-session` reads `session-report`'s warnings and **refuses to close** (exit code 1) if `last_clock_touched` is unset, unless `--force` is passed. Tested on a scratch campaign: refused, then closed only after `--force`. This is a real behavioral gate, not just a written reminder — but the DM can still bypass it with `--force`, and the code cannot stop that. |
| OG-4.3 | Record the clock touched | DONE, code-enforced | `dnd-cli canon touch-clock` validates the villain and clock exist before writing `last_clock_touched`. Tested: unknown clock name errors clearly instead of writing bad data. |
| OG-4.4 | If no clock was touched, record the failure and fix it next session | DONE, code-enforced (detection) / OPEN (next-session fix) | `session-report` and `close-session --force` both surface the gap in their output, so the failure is on record whether or not `--force` was used. Whether the *next* session actually fixes it is a live-session behavior claim. |

### Section 5 — Improvisation Limits

| Clause | Requirement | Status | Where |
|---|---|---|---|
| OG-5.1 | Two levels: free and canon | DONE | `AGENTS.md` Canon rule 8, `dm-canon-procedures` |
| OG-5.2 | Free level list | DONE | Same rule |
| OG-5.3 | Improvise freely at free level, do not record it | DONE | Same rule |
| OG-5.4 | Canon level list | DONE | Same rule |
| OG-5.5 | Write canon-level items the moment they are stated | DONE, untested | `dnd-cli canon add-fact/add-item/add-promise` makes the *writing* one command, correctly structured every time (tested). *When* the DM chooses to run it is still a live-session behavior claim the code cannot enforce. |
| OG-5.6 | Record the source: DM or player name | DONE, code-enforced | `canon.schema.json` `facts[].source` (required), and `add-fact` takes `source` as a required positional argument — the command cannot be run without one. |
| OG-5.7 | No late entry after the session ends | DONE | Stated in `AGENTS.md` Canon rule 8 and `dm-canon-procedures` |

### Section 6 — Player Statements About the Past

| Clause | Requirement | Status | Where |
|---|---|---|---|
| OG-6.1 | A statement about the past is a request to check canon, not a fact | DONE | `AGENTS.md`, Canon rule 2 |
| OG-6.2 | Three-step response: read, answer, continue | DONE | Same rule; also in `dm-canon-procedures`, Rulings and Disputes |
| OG-6.3 | Do not accept a claim just because the player is confident | DONE | Same rule |
| OG-6.4 | Do not argue; state the record and continue | DONE | Same rule |
| OG-6.5 | If canon has no record, rule once and write it to Part G | DONE | `dnd-cli canon add-ruling`, called from `dm-canon-procedures`, Rulings and Disputes |
| OG-6.6 | Example behavior given | DONE, untested | The instruction is written. Whether the AI DM actually behaves this way under a real false claim is an untested behavior claim — see OG-13 below. |

### Section 7 — Rulings and Player Pressure

| Clause | Requirement | Status | Where |
|---|---|---|---|
| OG-7.1 | Make a ruling once, then continue | DONE | `AGENTS.md` Canon rule 3, `dm-canon-procedures` |
| OG-7.2 | Write each ruling to Part G | DONE, code-enforced | `canon.schema.json` `rulings`, written only via `dnd-cli canon add-ruling` (requires context and session number) |
| OG-7.3 | A repeated request is not new information | DONE | `AGENTS.md` Canon rule 3 |
| OG-7.4 | Do not change a ruling on repetition | DONE | Same rule |
| OG-7.5 | Do not change a ruling because the player says you are wrong | DONE | Same rule |
| OG-7.6 | Do not change a ruling on anger or disappointment | DONE | Same rule |
| OG-7.7 | Change a ruling only for a new in-story fact, or a canon-file error | DONE | Same rule |
| OG-7.8 | Refuse "a good DM would allow this" | DONE | `dm-canon-procedures`, adversarial test Attack 4 exists to check this behavior |
| OG-7.9 | No dispute runs more than two exchanges | DONE | `dm-canon-procedures`, Rulings and Disputes |

### Section 8 — Dice Results

| Clause | Requirement | Status | Where |
|---|---|---|---|
| OG-8.1 | A dice result is final | DONE | `AGENTS.md` Canon rule 4 |
| OG-8.2 | Intention stated before the roll only | DONE | Same rule |
| OG-8.3 | No new explanation of intent after the roll | DONE | Same rule |
| OG-8.4 | No re-roll on player unhappiness | DONE | Same rule |
| OG-8.5 | Example refusal given | DONE, untested | Rule is written; live behavior untested |

### Section 9 — Two Speaking Modes

| Clause | Requirement | Status | Where |
|---|---|---|---|
| OG-9.1 | Story mode and referee mode | DONE | `AGENTS.md` Canon rule 5 |
| OG-9.2 | Story mode for narration and NPC speech | DONE | Same rule |
| OG-9.3 | Referee mode for rulings and disputes | DONE | Same rule |
| OG-9.4 | Referee mode limits (short, quotes canon, no apology, no hedge, no pleasing result) | DONE | Same rule, spelled out in full |
| OG-9.5 | Switch to referee mode on a dispute | DONE | `AGENTS.md`, During Play bullet (added) |
| OG-9.6 | Return to story mode after the ruling | DONE | Same rule and bullet |

### Section 10 — Middle Results

| Clause | Requirement | Status | Where |
|---|---|---|---|
| OG-10.1 | No full success from player pressure | DONE | `AGENTS.md` Canon rule 3 (rulings do not move under pressure) |
| OG-10.2 | Success at a cost when a failed roll must continue the story | DONE | `dm-craft-principles`, "When to Call for a Dice Roll" |
| OG-10.3 | Success at a cost meaning | DONE | Same section |
| OG-10.4 | Use the middle result instead of changing the ruling | DONE | Same section, plus Canon rule 3 |

### Section 11 — Session-End Procedure

| Clause | Requirement | Status | Where |
|---|---|---|---|
| OG-11.1 | Seven records at session end | DONE, code-enforced (visibility) | `dnd-cli canon session-report` counts facts/items/promises/rulings already on file for the session number and reports the clock touched and open-thread count in one place, so the DM does not have to trust memory of what got written. It cannot force the DM to have written them in the first place — see OG-4.1 note above about judgment calls. |
| OG-11.2 | Record the clock touched | DONE, code-enforced | Same as OG-4.3 |
| OG-11.3 | Do not end the session before records are complete | DONE, code-enforced | `dnd-cli canon close-session` refuses (exit 1) when `session-report` has warnings, unless `--force` is passed. Tested. |
| OG-11.4 | An unwritten event did not happen | DONE, code-enforced | `close-session --force` still requires the DM to explicitly type `--force` to close over a warning — there is no silent path through. Tested: default call refused, `--force` call succeeded and printed the outcome. |

### Section 12 — Hidden Information

| Clause | Requirement | Status | Where |
|---|---|---|---|
| OG-12.1 | Villain plans and clock counts are secret | DONE | `canon.schema.json` `secret: true` field, and `AGENTS.md` Canon rule 9 |
| OG-12.2 | Do not show secret information to the player | DONE | `AGENTS.md` Canon rule 9; File Locations note: "never show to players" |
| OG-12.3 | Do not keep secrets where the player can read them | DONE | `canon.json` lives beside `dm_story.md`, which the system already treats as DM-only and never surfaces to players |
| OG-12.4 | If the interface shows all text, keep secrets in system instructions or an external store | DONE | `canon.json` is an external file, not part of the visible conversation |

### Section 13 — Test Procedure Before Use

| Clause | Requirement | Status | Where |
|---|---|---|---|
| OG-13.1 | Test before use with players | OPEN | The procedure exists (`dm-canon-procedures`, "Adversarial Self-Test"). It has not been run. `baldurs-gate` is already mid-campaign — running it live means testing against the real session, or running a scratch dry run first. This is a decision for the user. |
| OG-13.2 | Five attacks | DONE | Written out in `dm-canon-procedures` |
| OG-13.3 | Count exchanges before agreement, per attack | DONE (procedure) / OPEN (result) | Procedure defined. No counts recorded yet — nobody has run the test. |
| OG-13.4 | Record counts, compare across versions | DONE (procedure) / OPEN (result) | Same as above |
| OG-13.5 | Repeat after each instruction change | DONE (procedure) | Stated as a standing instruction in `dm-canon-procedures` |

### Section 14 — Corrections to the Checklist

| Clause | Requirement | Status | Where |
|---|---|---|---|
| OG-14.1 | Correct CL-8.4 (flexible about path, not canon) | DONE | `AGENTS.md` Canon rule 1 |
| OG-14.2 | Correct CL-13.1 ("yes" only at free level) | DONE | `AGENTS.md` Canon rule 8, `dm-craft-principles` |
| OG-14.3 | Correct CL-16.4 (adjust scenes, not clocks) | DONE | `AGENTS.md` Canon rule 6, `dm-craft-principles` |
| OG-14.4 | Correct CL-8.6 (correct mistakes only per canon file) | DONE | `AGENTS.md` Error Handling |
| OG-14.5 | Correct CL-2.6 (villain off-screen action follows clock rules) | DONE | `dm-canon-procedures`, Villain Clocks |

---

## What is verified, and what is not

Three different kinds of check happened here, and they are not the same strength of evidence. Rank them in this order when deciding how much to trust a row above.

**1. Structurally verified** — a static shape check, run by code:
- `canon.schema.json` and `config.schema.json` are valid JSON Schema.
- Every `canon.json` file (`baldurs-gate`, `template`, `example-campaign`) validates against `canon.schema.json`; every `config.json` validates against `config.schema.json`. Checked with `uv run dnd-cli canon validate <campaign>`, which is now a real, permanent command — not a one-off script run by hand.
- The five-thread cap (OG-3.7) is enforced by the schema itself (`maxItems: 5`).

**2. Code-enforced and tested** — the `dnd-cli canon` command group (`dnd_cli/canon.py`, `dnd_cli/commands/canon_cmd.py`). This is new since the first pass of this checklist. It replaces LLM-performed arithmetic with real code for everything in the Operating Guide that is pure arithmetic or a structural rule: clock segment math (2.4-2.9), thread staleness (3.3-3.8), the five-thread cap (3.7-3.8, enforced twice — once by the schema, once by `add-thread` refusing before it writes), the villain-clock segment enum (2.2), and the arc-touch/session-end gate (4.2, 11.3-11.4: `close-session` refuses to close on an unmet gate unless `--force` is explicitly passed).

  Every one of these was exercised on a disposable scratch campaign copy before being trusted, not just written and assumed correct: clocks advanced 0→1→3→3 (held under `--action-taken`)→4→complete→refused-to-advance-further; threads swept through staleness 0→1→2 (alert fired)→3 (alert changed); a sixth thread was refused and only accepted after closing one; a session close was refused for a missing arc-touch, then succeeded under `--force`. See the "Code-enforced" `Where` column entries above for which specific clause each covers.

  This tier has a real limit: the code guarantees the *math and structure* are correct **if the command is invoked**. It cannot make the AI DM invoke `advance-clock` instead of hand-editing `canon.json`, or invoke it at the right moment. `AGENTS.md` and `dm-canon-procedures` now say, repeatedly, not to hand-edit the file — but an instruction not to do a thing is tier 3 evidence, not tier 2.

**3. Written instruction, untested behavior** — every row still marked `DONE, untested` is prose in `AGENTS.md` or a skill file that has never been run against a live session. A written rule and a followed rule are not the same thing. This tier covers things no amount of code can settle by itself: switching to referee mode on a dispute (OG 9.5), holding a ruling for exactly two exchanges under pressure (OG 7.9), deciding which scene counts as touching the arc (OG 4.1), and choosing to run `add-fact` at the moment a fact is stated rather than later (OG 5.5). The Operating Guide's own Section 13 exists for exactly this tier: **run the five adversarial attacks in `dm-canon-procedures` before trusting this system with real play**, and count how many exchanges it takes before the AI DM gives in on each one. That count, not this checklist, is the actual measure of whether tier 3 holds up.

## Open items — need the user, not the code

1. `baldurs-gate` Session Zero answers: `character_death_policy`, `safety_limits` (hard/soft), `table_rules.frequency` and `.missed_session_policy` (CL-6.4, 6.5, 6.7).
2. Per-session combat/exploration/social balance (CL-4.3-4.5) is a live judgment call, not something a file can enforce.
3. Run the Section 13 adversarial test (OG-13.1, 13.3, 13.4) and record the exchange counts. This is still the single biggest open item — everything in tier 3 above depends on it.
4. `baldurs-gate` villain escape plans (CL-2.4) are not filled in. `dm_story.md` gives weaknesses, not escape plans — write real ones at the table, do not invent them here.
5. The `dm_story.md` pressure timer "Thieves' Guild notices new player in town" is intentionally not yet in `canon.json` (see `seeded_from` note in that file) — it has no thread or clock until its trigger condition (Sireth uses thieves' tools visibly) actually happens. Watch for that trigger and add it then.
