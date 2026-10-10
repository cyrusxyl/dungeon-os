"""Level 1 character creation: one call builds the whole sheet from the player's choices.

The DM talks the choices through with the player. This module does the
arithmetic (scores, HP, AC, skills, saves, spell numbers) and fills in the
race, class and gear data from the 5e API. `fetch(endpoint) -> dict` is passed
in, and raises RulesError when the endpoint does not exist, so tests can stub it.
"""

from __future__ import annotations

import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from dnd_cli import character, dice, sheet
from dnd_cli.combat import ABILITIES, SKILLS, RulesError, ability, load_state, save_state
from stage.files import read_json, write_json


def slug(text: str) -> str:
    return re.sub(r"[\s_]+", "-", text.strip().lower())


def _skill(name: str) -> str:
    key = slug(name).removeprefix("skill:-").removeprefix("skill-").replace("-", "_")
    if key not in SKILLS:
        raise RulesError(f"no skill {name!r}. Use one of: {', '.join(SKILLS)}.")
    return key


def _skills(text: str | None) -> list[str]:
    return [_skill(s) for s in (text or "").split(",") if s.strip()]


def _names(text: str | None) -> list[str]:
    return [s.strip() for s in (text or "").split(",") if s.strip()]


def _title(index: str) -> str:
    return index.replace("-", " ").title() if index == index.lower() else index


def _first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0]


def _lookup(fetch, endpoint: str, what: str) -> dict:
    try:
        return fetch(endpoint)
    except RulesError:
        raise RulesError(f"no {what} {endpoint.split('/')[-1]!r} in the 5e API. "
                         f"Find the index with: uv run dnd-cli search {endpoint.split('/')[0]} --name <word>") from None


def _desc(fetch, endpoint: str) -> str:
    try:
        d = fetch(endpoint).get("desc") or [""]
    except RulesError:
        return ""
    return _first_sentence(d[0] if isinstance(d, list) else d)


def _class_skill_options(cls: dict) -> tuple[int, list[str]]:
    for ch in cls.get("proficiency_choices", []):
        opts = [o["item"]["index"] for o in ch["from"]["options"]
                if o.get("option_type") == "reference" and o["item"]["index"].startswith("skill-")]
        if opts:
            return ch["choose"], [_skill(o) for o in opts]
    return 0, []


def _scores(scores: str, assign: str, race_bonuses: list[tuple[str, int]]) -> dict:
    try:
        values = [int(x) for x in scores.split(",")]
    except ValueError:
        values = []
    if len(values) != 6 or not all(3 <= v <= 18 for v in values):
        raise RulesError(f"--scores {scores!r}: give six numbers from 3 to 18, like 15,14,13,12,10,8.")
    order = [ability(a) for a in assign.split(",")]
    if sorted(order) != sorted(ABILITIES):
        raise RulesError(f"--assign {assign!r}: name each of str,dex,con,int,wis,cha once, "
                         "in the order of the scores (the first score goes to the first ability).")
    out = dict(zip(order, values))
    for abil, bonus in race_bonuses:
        out[abil] = min(20, out[abil] + bonus)
    return {a: out[a] for a in ABILITIES}


def build(fetch, *, player: str, name: str, race: str, cls: str, background: str, scores: str, assign: str,
          skills: str, subrace: str | None = None, background_skills: str | None = None,
          cantrips: str | None = None, spells: str | None = None, equipment: str | None = None,
          alignment: str = "", languages: str | None = None, bonus_abilities: str | None = None) -> dict:
    """Return a level 1 sheet. Raises RulesError, with a message that says how to fix the call."""
    r = _lookup(fetch, f"races/{slug(race)}", "race")
    sub = _lookup(fetch, f"subraces/{slug(subrace)}", "subrace") if subrace else {}
    c = _lookup(fetch, f"classes/{slug(cls)}", "class")
    lvl = _lookup(fetch, f"classes/{c['index']}/levels/1", "class level")

    bonuses = [(ability(b["ability_score"]["index"]), b["bonus"]) for b in r.get("ability_bonuses", []) + sub.get("ability_bonuses", [])]
    opt = r.get("ability_bonus_options")
    if opt:
        picked = [ability(a) for a in _names(bonus_abilities)]
        allowed = {ability(o["ability_score"]["index"]) for o in opt["from"]["options"]}
        if len(set(picked)) != opt["choose"] or not set(picked) <= allowed:
            raise RulesError(f"{r['name']} adds +1 to {opt['choose']} different abilities: give --bonus-abilities "
                             f"with {opt['choose']} of {','.join(a[:3] for a in ABILITIES if a in allowed)}.")
        bonuses += [(a, 1) for a in picked]
    scores_final = _scores(scores, assign, bonuses)
    m = {a: dice.mod(v) for a, v in scores_final.items()}

    # skills
    need, options = _class_skill_options(c)
    chosen = _skills(skills)
    if len(chosen) != need or len(set(chosen)) != need or not set(chosen) <= set(options):
        raise RulesError(f"{c['name']} picks {need} different skills from: {', '.join(options)}. "
                         f"Fix --skills (got {skills!r}).")
    try:
        bg = fetch(f"backgrounds/{slug(background)}")
    except RulesError:
        bg = None
    bg_skills = [_skill(p["index"]) for p in (bg or {}).get("starting_proficiencies", []) if p["index"].startswith("skill-")]
    bg_skills += [s for s in _skills(background_skills) if s not in bg_skills]
    if bg is None and not bg_skills:
        raise RulesError(f"background {background!r} is not in the 5e API. Add its two skills with --background-skills a,b.")
    race_skills = [_skill(p["index"]) for p in r.get("starting_proficiencies", []) if p["index"].startswith("skill-")]
    if any(t["index"] == "keen-senses" for t in r.get("traits", [])):
        race_skills.append("perception")
    clash = (set(chosen) & set(bg_skills)) | ((set(chosen) | set(bg_skills)) & set(race_skills))
    if clash:
        raise RulesError(f"{', '.join(sorted(clash))} comes from two sources. Pick another class skill, "
                         "or another skill in --background-skills.")
    prof = sheet.prof_for_level(1)
    proficient = [*chosen, *bg_skills, *race_skills]

    die = c["hit_die"]
    saves = [ability(s["index"]) for s in c.get("saving_throws", [])]
    data = {
        "name": name, "controlled_by": player,
        "race": f"{r['name']} ({sub['name']})" if sub else r["name"],
        "class": c["name"], "level": 1, "background": background, "alignment": alignment,
        "experience_points": 0,
        "ability_scores": scores_final, "ability_modifiers": m, "proficiency_bonus": prof,
        "skills": {s: m[SKILLS[s]] + prof for s in proficient},
        "saving_throws": {a: m[a] + prof for a in saves},
        "hp": {"current": max(1, die + m["constitution"]), "max": max(1, die + m["constitution"]), "temp": 0},
        "armor_class": sheet.base_ac(c["name"], m), "initiative": m["dexterity"], "speed": r.get("speed", 30),
        "hit_dice": {"total": 1, "remaining": 1, "type": f"d{die}"},
        "death_saves": {"successes": 0, "failures": 0},
        "languages": [*(_l["name"] for _l in r.get("languages", [])), *(_title(x) for x in _names(languages))],
        "inventory": [], "weapons": [],
    }
    if not alignment:
        del data["alignment"]

    for idx, n in Counter(slug(i) for i in _names(equipment)).items():  # a repeated index is a quantity
        item = _lookup(fetch, f"equipment/{idx}", "equipment")
        sheet.equip(data, item)
        if n > 1:
            sheet.add_item(data, item["name"], n - 1)

    traits = [(t["name"], f"traits/{t['index']}") for t in r.get("traits", []) + sub.get("racial_traits", [])]
    feats = [(f["name"], f"features/{f['index']}") for f in lvl.get("features", [])]
    seen, data["features_and_traits"] = set(), []
    for fname, endpoint in traits + feats:
        if fname not in seen:
            seen.add(fname)
            data["features_and_traits"].append({"name": fname, "description": _desc(fetch, endpoint)})
    if sheet.hp_bonus_per_level(data):
        data["hp"]["max"] += 1
        data["hp"]["current"] += 1

    sc = lvl.get("spellcasting") or {}
    slots = {str(i): {"max": sc[f"spell_slots_level_{i}"], "remaining": sc[f"spell_slots_level_{i}"]}
             for i in range(1, 10) if sc.get(f"spell_slots_level_{i}")}
    if slots or sc.get("cantrips_known"):
        abil = ability((c.get("spellcasting") or {}).get("spellcasting_ability", {}).get("index", "int"))
        data["spellcasting"] = {
            "ability": abil, "spell_save_dc": 8 + prof + m[abil], "spell_attack_bonus": prof + m[abil],
            "spell_slots": slots, "spells_known": [_title(s) for s in [*_names(cantrips), *_names(spells)]],
        }
    elif cantrips or spells:
        raise RulesError(f"{c['name']} has no spells at level 1. Remove --cantrips and --spells.")
    return data


def describe(data: dict) -> list[str]:
    """Short result lines for the DM."""
    s = data["ability_scores"]
    lines = [f"{data['name']}: {data['race']} {data['class']} 1 ({data['background']}), HP {data['hp']['max']}, "
             f"AC {data['armor_class']}, " + " ".join(f"{a[:3].upper()} {s[a]}" for a in ABILITIES)]
    sp = data.get("spellcasting")
    if sp:
        lines.append(f"spell save DC {sp['spell_save_dc']}, attack {dice.signed(sp['spell_attack_bonus'])}, "
                     f"{len(sp['spells_known'])} spells known")
    lines.append("Still to ask the player: personality traits, ideals, bonds, flaws. "
                 "Add them to the sheet with the Edit tool.")
    return lines


def register(campaign_dir: Path, char_id: str, player: str, player_name: str | None) -> None:
    """Add the character to state.json party_members and to the player's file."""
    state = load_state(campaign_dir)
    if "party_members" not in state:  # seed with the sheets that exist, or they would leave the party
        state["party_members"] = [p.stem for p in sorted((campaign_dir / "characters").glob("*.json"))
                                  if p.stem != char_id]
    if char_id not in state["party_members"]:
        state["party_members"].append(char_id)
    save_state(campaign_dir, state)

    path = campaign_dir / "players" / f"{player}.json"
    path.parent.mkdir(exist_ok=True)
    pdata = read_json(path) or {
        "player_id": player, "player_name": player_name or player, "characters_controlled": [],
        "permissions": {"can_edit_own_characters": True, "can_view_other_sheets": False, "can_edit_world": False},
        "joined_date": date.today().isoformat(),
    }
    if char_id not in pdata["characters_controlled"]:
        pdata["characters_controlled"].append(char_id)
    write_json(path, pdata, indent=2)


def create(campaign_dir: Path, fetch, char_id: str, player_name: str | None = None, **choices) -> list[str]:
    if character.character_path(campaign_dir, char_id).exists():
        raise RulesError(f"characters/{char_id}.json already exists. Pick another id.")
    data = build(fetch, **choices)
    (campaign_dir / "characters").mkdir(exist_ok=True)
    character.save(campaign_dir, char_id, data)
    register(campaign_dir, char_id, choices["player"], player_name)
    return describe(data)


# -- options for the web creator ----------------------------------------------

HAIR_STYLES = ("hair_plain", "hair_long", "hair_curly_short", "hair_spiked", "hair_shorthawk",
               "hair_ponytail", "hair_bob", "hair_braid", "hair_pixie", "hair_buzzcut")
HAIR_COLORS = ("platinum", "blonde", "ginger", "red", "light_brown", "chestnut", "dark_brown", "black", "gray", "white")


def _bonuses(data: dict) -> dict[str, int]:
    return {ability(b["ability_score"]["index"]): b["bonus"] for b in data.get("ability_bonuses", [])}


MAX_GEAR_OPTIONS = 80


def _gear_sets(fetch, o: dict) -> list[list[tuple[str, str, int]]]:
    """The alternatives one API option stands for, each a list of (index, name, count). A nested choice from a category
    ("a martial weapon") gives one alternative per item of the category. [] means the stage cannot read the option."""
    kind = o.get("option_type")
    if kind == "counted_reference":
        return [[(o["of"]["index"], o["of"]["name"], o["count"])]]
    if kind == "choice":
        ch = o["choice"]
        src = ch.get("from", {})
        if src.get("option_set_type") == "equipment_category":
            cat = fetch(f"equipment-categories/{src['equipment_category']['index']}")
            return [[(e["index"], e["name"], ch.get("choose", 1))] for e in cat.get("equipment", [])]
        if src.get("option_set_type") == "options_array" and ch.get("choose", 1) == 1:
            return [s for sub in src["options"] for s in _gear_sets(fetch, sub)]
        return []
    if kind == "multiple":
        sets = [[]]
        for item in o["items"]:
            alts = _gear_sets(fetch, item)
            if not alts:
                return []
            sets = [a + b for a in sets for b in alts]
            if len(sets) > MAX_GEAR_OPTIONS:
                return []
        return sets
    return []


def _gear_option(items: list[tuple[str, str, int]]) -> dict:
    """One option for the creator: the indexes joined by commas (a repeat is a quantity), and a name to read."""
    name = ", ".join(n if c == 1 else f"{n} \u00d7{c}" for _, n, c in items)
    return {"index": ",".join(i for i, _, c in items for _ in range(c)), "name": name}


def _simple_choices(fetch, cls: dict) -> list[dict]:
    """The starting-gear choices of a class: pick one of several sets of items. The stage skips a choice it cannot read
    (the DM can hand out the gear later)."""
    out = []
    for ch in cls.get("starting_equipment_options", []):
        src = ch.get("from", {})
        if ch.get("choose") != 1 or src.get("option_set_type") != "options_array":
            continue
        sets = [s for o in src["options"] for s in _gear_sets(fetch, o)]
        if 1 < len(sets) <= MAX_GEAR_OPTIONS:
            out.append({"label": re.sub(r"\([a-z]\)\s*", "", ch["desc"]), "options": [_gear_option(s) for s in sets]})
    return out


def _spell_options(fetch, cls: str, level: int) -> list[dict]:
    spells = fetch(f"classes/{cls}/spells")["results"]
    return [{"index": x["index"], "name": x["name"]} for x in spells if x.get("level") == level]


def _class_options(fetch, index: str) -> dict:
    c = fetch(f"classes/{index}")
    sc = fetch(f"classes/{index}/levels/1").get("spellcasting") or {}
    n, skills = _class_skill_options(c)
    out = {
        "index": index, "name": c["name"], "hit_die": c["hit_die"],
        "saves": [ability(s["index"]) for s in c.get("saving_throws", [])],
        "skill_count": n, "skill_options": skills, "spellcasting": None,
        "equipment": {"fixed": [{"index": e["equipment"]["index"], "name": e["equipment"]["name"], "quantity": e["quantity"]}
                                for e in c.get("starting_equipment", [])],
                      "choices": _simple_choices(fetch, c)},
    }
    if sc.get("cantrips_known") or any(sc.get(f"spell_slots_level_{i}") for i in range(1, 10)):
        out["spellcasting"] = {
            "ability": ability(c["spellcasting"]["spellcasting_ability"]["index"]),
            "cantrips": sc.get("cantrips_known", 0),
            # A prepared caster (cleric, druid) picks none here; the wizard's spellbook holds six.
            "spells": sc.get("spells_known", 6 if index == "wizard" else 0),
            "cantrip_options": _spell_options(fetch, index, 0),
            "spell_options": _spell_options(fetch, index, 1),
        }
    return out


def _race_options(fetch, index: str) -> dict:
    from stage import actors

    r = fetch(f"races/{index}")
    opt = r.get("ability_bonus_options")
    return {
        "index": index, "name": r["name"], "speed": r.get("speed", 30), "ability_bonuses": _bonuses(r),
        "bonus_choice": opt and {"count": opt["choose"],
                                 "options": [ability(o["ability_score"]["index"]) for o in opt["from"]["options"]]},
        "subraces": [{"index": s["index"], "name": sub["name"], "ability_bonuses": _bonuses(sub)}
                     for s in r.get("subraces", []) for sub in [fetch(f"subraces/{s['index']}")]],
        "look_race": actors.race_of(r["name"]) or "human",
    }


def _background_options(fetch, index: str) -> dict:
    b = fetch(f"backgrounds/{index}")
    return {"index": index, "name": b["name"],
            "skills": [_skill(p["index"]) for p in b.get("starting_proficiencies", []) if p["index"].startswith("skill-")]}


def _look_options() -> dict:
    from stage import actors, lpc

    colors = lpc.catalog()["hair_long"].colors()
    return {
        "bodies": ["male", "female", "muscular"],
        "eyes": lpc.palette_names("eye"),
        "races": {k: {"skins": v["skins"], "default_skin": v.get("skin", v["skins"][0])} for k, v in actors.races().items()},
        "hair": [{"id": h, "name": h.removeprefix("hair_").replace("_", " ").title()} for h in HAIR_STYLES],
        "hair_colors": [c for c in HAIR_COLORS if c in colors],
    }


def options(fetch) -> dict:
    """The document behind the web creator: every choice `build` accepts at level 1. Raises RulesError."""
    def indexes(resource: str) -> list[str]:
        return [x["index"] for x in fetch(resource)["results"]]

    with ThreadPoolExecutor(8) as pool:  # a cold cache is about fifty small requests
        races = pool.map(lambda i: _race_options(fetch, i), indexes("races"))
        classes = pool.map(lambda i: _class_options(fetch, i), indexes("classes"))
        backgrounds = pool.map(lambda i: _background_options(fetch, i), indexes("backgrounds"))
        return {"races": list(races), "classes": list(classes), "backgrounds": list(backgrounds),
                "skills": list(SKILLS), "abilities": list(ABILITIES), "look": _look_options()}
