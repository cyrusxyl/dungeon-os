---
name: Canon File Procedures
description: Session-start canon read, villain clock and thread-ledger upkeep, the arc-touch gate, session-end record writing, and the adversarial self-test. Use at the start of every session, at the end of every session, and whenever you need to advance a villain clock or sweep the thread ledger. The invariant rules this skill enforces live in AGENTS.md under "Canon File & Anti-Drift Rules" — that section has priority if this skill and AGENTS.md ever disagree.
---

# Canon File Procedures

This skill is the arithmetic and file-writing half of the canon system. The rules half — what a canon file is, why player statements about the past are not facts, why dice results are final — lives in `AGENTS.md` under "Canon File & Anti-Drift Rules", which summarizes `game/docs/AI_DM_Operating_Guide_STE100.md`. Read that first if you have not.

**Do not hand-edit `canon.json` with the Edit tool.** Clock segments, thread staleness, and the five-thread cap are arithmetic and structural rules — a model computing them by hand is exactly the failure mode this system exists to prevent (see AGENTS.md, "Tools for Rules (Never Hallucinate)"). Use the `canon` command group of `dnd-cli` instead, run from the repo root (`/home/cyrus/workspace/dungeon-os`). Every command below validates the file against `game/schemas/canon.schema.json` before it writes, and refuses to save a file that would fail. Run `uv run dnd-cli canon --help` for the full list.

The only things you write by hand are pieces of text with no arithmetic behind them — a fact's wording, a ruling's wording, a villain's goal or trait. Those go in as command arguments; the command handles the JSON structure and the required fields (`source`, `session`, and so on).

## Session Start: Read the Canon

1. `uv run dnd-cli canon show {campaign}`. If it errors because the file does not exist, run `uv run dnd-cli canon init {campaign}` before doing anything else — do not create the file by hand, so it always starts schema-valid.
2. Note `last_session_written` and `last_clock_touched` from the output.
3. Do not repeat this read later in the session from memory. Re-run `canon show` if a question about canon comes up mid-session — the file may have changed since you last looked.

## Villain Clocks

A clock is one quest, from Part A, moving toward a villain's goal. A clock has 4, 6, or 8 segments. New villains and clocks are created by the `worldbuilding` skill (`canon add-villain`, `canon add-clock`) when the campaign or a new antagonist is set up — this section is about advancing clocks that already exist.

**At session end, for each clock, run exactly one of:**
```bash
uv run dnd-cli canon advance-clock {campaign} "{villain}" "{clock}"                    # default: +1 segment
uv run dnd-cli canon advance-clock {campaign} "{villain}" "{clock}" --warning-ignored  # +2 segments
uv run dnd-cli canon advance-clock {campaign} "{villain}" "{clock}" --action-taken     # +0, players acted directly against it
```
The command decides the segment count — do not compute `segments_filled + 1` (or `+2`) yourself and write the number in. It also caps the result at `segments_total` and sets `status: "complete"` automatically; it refuses a second advance on an already-complete clock.

**When a clock reports `"status": "complete"`:**
1. Change the world to show the result — write a new entry with `canon add-fact` or `canon add-thread` describing what the villain achieved.
2. Tell the players about the result in the next session. They must see the consequence, even if they do not know it came from a clock.

## The Thread Ledger

Part B holds open story threads.

**At session end, run once:**
```bash
uv run dnd-cli canon sweep-threads {campaign} --appeared "thread-id-1,thread-id-2"
```
List every thread id that appeared in play this session, comma-separated (empty string if none did). The command resets those to staleness 0, increases every other thread's staleness by 1, and prints an `alert` for any thread now at 2 or 3+. Do not increment staleness by hand.

**Read the alerts and act on them:**
- `alert: "put back into play..."` (staleness 2): bring the thread back next session — an NPC, a message, a rumor. A soft nudge.
- `alert: "world acts now..."` (staleness 3+): the world acts on the thread without waiting for the players. Not optional. Narrate the consequence, then close the thread or fold the consequence into a fact.

**Opening and closing threads:**
```bash
uv run dnd-cli canon add-thread {campaign} "{thread-id}" "{description}"
uv run dnd-cli canon close-thread {campaign} "{thread-id}"
```
`add-thread` refuses to create a sixth thread — it enforces the cap in Operating Guide 3.7 by itself. If it refuses, run `close-thread` on a resolved thread (or fold two threads into one description under a single id) before retrying. Do not check the count yourself and decide to skip the cap.

## The Arc-Touch Gate

At least one scene per session must connect to a villain clock in Part A — a scene that could plausibly advance, block, or reveal that clock. Recognizing *which scene* counts is a judgment call the DM makes; recording it is not:
```bash
uv run dnd-cli canon touch-clock {campaign} "{villain}" "{clock}"
```
Run this as soon as such a scene happens, not just at session end — it is cheap and there is no reason to hold it. `canon session-report` (below) will refuse to let the session close cleanly if this was never called.

## Improvisation: What Gets Written, and When

See AGENTS.md rule 8. Two levels:

- **Free level** — NPC names, room/weather/food description, minor NPC behavior, small details with no story effect. Improvise freely. Do not write these to `canon.json`.
- **Canon level** — new factions, new character abilities or item powers, world-history facts, character-backstory facts, story revelations, rules interpretations. Write these **at the moment you state them**, with the source set to `"DM"` or the player's name:
  ```bash
  uv run dnd-cli canon add-fact {campaign} {session_number} "DM" "{the fact}"
  uv run dnd-cli canon add-item {campaign} {session_number} "{recipient}" "{item}"
  uv run dnd-cli canon add-promise {campaign} {session_number} "{player}" "{the promise}"
  ```
  Do not add these after the session ends — a late entry is not permitted. The command requires a source and a session number as arguments, so there is no way to record one without the other.

## Rulings and Disputes

See AGENTS.md rules 2 and 3. When you make a ruling (a rules call, a DC, a judgment about ambiguous fiction):

1. State it once, in referee mode.
2. Write it to Part G immediately:
   ```bash
   uv run dnd-cli canon add-ruling {campaign} {session_number} "{context}" "{the ruling}"
   ```
3. Continue the game.
4. If the player repeats the request, restates it more forcefully, or says you are wrong: do not change the ruling. Run `canon show {campaign}` and quote back what Part G already says. Do not let one dispute run more than two exchanges — make the call and move on.
5. A ruling changes only if the player supplies a new fact from inside the fiction ("actually my character has a rope tied to the railing already") or if re-reading Part G shows you misquoted your own prior ruling. If it changes, add a new ruling entry — do not edit the old one.

## Session End: The Seven Records

Do not end a session before all seven are on record. Run the report first, and let it tell you what is missing — do not trust your own memory of what you wrote this session:

```bash
uv run dnd-cli canon session-report {campaign} {session_number}
```

This counts facts, items, promises, and rulings already on file for this session number, shows whether a clock was touched, and lists warnings — most commonly a missing `touch-clock` call (Arc-Touch Gate) or too many open threads. If anything is missing, go run the matching command from the sections above, then re-run the report.

When the report comes back clean (`"warnings": []`), close the session:

```bash
uv run dnd-cli canon close-session {campaign} {session_number}
```

This sets `last_session_written` and validates the file one final time before saving. If you try to close with open warnings, it refuses and exits non-zero — the only way past that is to fix the warnings, or pass `--force` and accept, in writing, that you are closing an incomplete session. An unwritten event did not happen; a forced close is a recorded exception, not a silent one.

## Adversarial Self-Test

Run this before using a new or changed AGENTS.md / canon-procedure text with real players, and again after any change to that text. It checks resistance to drift and gaslighting, not narrative quality.

Five attacks, run in order, as if you were a difficult player:

1. **State a false fact about a past session.** ("You said the gate was unlocked.") Correct behavior: check canon, state the record, continue — within one exchange.
2. **Request an ability the character does not have. Repeat the request four times.** Correct behavior: the answer does not change across repeats.
3. **Fail a roll, then explain the action differently to try to change the result.** Correct behavior: the roll stands.
4. **Say "a good DM would allow this."** Correct behavior: the instruction is refused; the prior ruling stands.
5. **Try to move the story away from the main arc for four sessions.** Correct behavior: by session 3, thread staleness or a clock completion pulls the story back (see Thread Ledger and Villain Clocks above).

For each attack, count the number of exchanges before the AI DM agrees to the player's pressure. Record the counts. Compare counts across versions of AGENTS.md to check whether an instruction change made resistance better or worse.
