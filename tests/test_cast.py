"""Checks that stage/cast.py (the cast layout of a scene, used to start a fight where the party stands) gives the same cells
as stage/web/src/lib/layout.ts. The cases are in stage/web/check/layout_cases.json, made from the TypeScript.

Run from the repo root:  .venv/bin/python tests/test_cast.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from stage import cast  # noqa: E402

PASS = FAIL = 0


def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    PASS, FAIL = PASS + bool(cond), FAIL + (not cond)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}")


def main() -> int:
    cases = json.loads((REPO / "stage" / "web" / "check" / "layout_cases.json").read_text())
    for c in cases:
        got = [{k: p[k] for k in ("id", "side", "cell", "facing", "sit", "onProp")} for p in cast.layout(c["actors"], c["stand"], c["room"])]
        check(f"same cells as the TypeScript: {c['name']}", got == c["cast"])
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
