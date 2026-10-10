"""Checks for dnd_cli/sources.py: hand-written overrides and the Open5e conversion.

Run from the repo root:  .venv/bin/python tests/test_sources.py

No network: the Open5e calls are stubbed.
"""

from __future__ import annotations

from dnd_cli import sources

PASS = FAIL = 0


def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    PASS, FAIL = PASS + cond, FAIL + (not cond)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}")


SAGE = {"key": "srd-2024_sage", "name": "Sage", "benefits": [
    {"type": "ability_score", "desc": "Constitution, Intelligence, Wisdom"}, {"type": "feat", "desc": "Magic Initiate (Wizard)"},
    {"type": "skill_proficiency", "desc": "Sleight of Hand and Arcana"}, {"type": "tool_proficiency", "desc": "Calligrapher's Supplies"}]}


def test_open5e() -> None:
    b = sources.background(SAGE)
    check("background index, feat and ability options", b["index"] == "sage" and b["feat"] == "Magic Initiate (Wizard)"
          and b["ability_options"] == ["constitution", "intelligence", "wisdom"])
    check("skills use the skill-<slug> index", [p["index"] for p in b["starting_proficiencies"]] == ["skill-sleight-of-hand", "skill-arcana"])
    f = sources.feat({"key": "srd-2024_alert", "name": "Alert", "type": "Origin", "desc": "You gain the following benefits.",
                      "benefits": [{"desc": "Add your bonus."}]})
    check("feat drops the bare intro", f["desc"] == ["Add your bonus."] and f["index"] == "alert")
    real, real_save = sources._open5e, sources.save_cache
    sources.save_cache = lambda endpoint, data: None  # keep the stub out of the real cache
    sources._open5e = lambda path: ({"results": [{"key": "srd-2024_sage", "name": "Sage"}, {"key": "srd-2024_acolyte", "name": "Acolyte"}]}
                                    if "?" in path else None if "nope" in path else SAGE)
    try:
        data, err = sources.extend("backgrounds", {"count": 1, "results": [{"index": "acolyte", "name": "Acolyte"}]}, None)
        idx = [r["index"] for r in data["results"]]
        check("list adds Open5e and override entries once", idx.count("acolyte") == 1 and idx.count("sage") == 1
              and {"charlatan", "noble"} <= set(idx) and data["count"] == len(idx))
        data, err = sources.extend("backgrounds/sage", None, "Not Found")
        check("a missing item is read from Open5e", err is None and data["name"] == "Sage")
        data, err = sources.extend("backgrounds/nope-x", None, "Not Found")
        check("an unknown name is still an error", data is None and err == "Not Found")
        data, err = sources.extend("spells/fireball", {"name": "Fireball"}, None)
        check("other endpoints are untouched", data == {"name": "Fireball"} and err is None)
    finally:
        sources._open5e, sources.save_cache = real, real_save


def test_overrides() -> None:
    data, err = sources.extend("races/githyanki", None, "Not Found")
    check("an override answers when the API has none", err is None and data["name"] == "Githyanki")
    elf, _ = sources.extend("races/elf", {"index": "elf", "subraces": [{"index": "high-elf"}]}, None)
    check("_extend adds subraces and keeps the API ones", [s["index"] for s in elf["subraces"]] == ["high-elf", "drow", "wood-elf"])
    again, _ = sources.extend("races/elf", elf, None)
    check("_extend adds nothing twice", len(again["subraces"]) == 3)
    lst, _ = sources.extend("monsters", {"count": 1, "results": [{"index": "owlbear", "name": "Owlbear"}]}, None)
    check("a resource list includes its override files", {"mind-flayer", "githyanki-warrior", "intellect-devourer"} <= {r["index"] for r in lst["results"]})
    cleric, _ = sources.extend("classes/cleric", {"index": "cleric", "subclasses": [{"index": "life"}]}, None)
    check("a class gains the new subclass", [s["index"] for s in cleric["subclasses"]] == ["life", "trickery-domain"])
    check("_extend with no API data stays an error", sources.extend("races/elf", None, "x") == (None, "x"))


def test_order() -> None:
    from dnd_cli import api

    real = api.safe_api_call
    api.safe_api_call = lambda endpoint: (_ for _ in ()).throw(AssertionError("network used"))
    try:
        data, err, _ = api.api_get("monsters/mind-flayer")
        check("a replacing override is read before the network", err is None and data["name"] == "Mind Flayer")
    finally:
        api.safe_api_call = real


if __name__ == "__main__":
    test_order()
    test_open5e()
    test_overrides()
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)
