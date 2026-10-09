"""Dice: `XdY+XdY+K` expressions, advantage, and critical hits.

The rules commands (attack, save, check, rest) roll here, so the DM never
adds dice in its head. `rng` is injectable for tests.
"""

from __future__ import annotations

import random
import re

TERM = re.compile(r"([+-])?\s*(?:(\d*)d(\d+)|(\d+))")


class DiceError(ValueError):
    """A dice expression the roller cannot read."""


def parse(expr: str) -> tuple[list[tuple[int, int, int]], int]:
    """`2d6+1d4+3` -> ([(sign, count, sides), ...], flat bonus)."""
    text = expr.replace(" ", "").lower()
    if not text:
        raise DiceError("empty dice expression")
    dice, flat, pos = [], 0, 0
    while pos < len(text):
        m = TERM.match(text, pos)
        if not m or m.end() == pos or (pos > 0 and not m.group(1)):
            raise DiceError(f"cannot read dice {expr!r}; write it like 2d6+3")
        sign = -1 if m.group(1) == "-" else 1
        if m.group(3):
            dice.append((sign, int(m.group(2) or 1), int(m.group(3))))
        else:
            flat += sign * int(m.group(4))
        pos = m.end()
    return dice, flat


def average(expr: str) -> float:
    """The average of a dice expression like 2d8+2."""
    terms, flat = parse(expr)
    return flat + sum(sign * count * (sides + 1) / 2 for sign, count, sides in terms)


def roll(expr: str, rng: random.Random | None = None, crit: bool = False) -> tuple[int, list[dict]]:
    """Total and the faces per die group. A critical hit rolls each die group twice."""
    rng = rng or random
    dice, flat = parse(expr)
    total, groups = flat, []
    for sign, count, sides in dice:
        n = count * 2 if crit else count
        faces = [rng.randint(1, sides) for _ in range(n)]
        total += sign * sum(faces)
        groups.append({"die": f"{n}d{sides}", "faces": faces})
    return max(total, 0), groups


def d20(rng: random.Random | None = None, adv: bool = False, dis: bool = False) -> tuple[int, list[int]]:
    """The d20 that counts, and every d20 rolled (two with advantage or disadvantage)."""
    rng = rng or random
    if adv and dis:
        adv = dis = False
    faces = [rng.randint(1, 20) for _ in range(2 if adv or dis else 1)]
    return (max(faces) if adv else min(faces) if dis else faces[0]), faces


def mod(score: int) -> int:
    return (score - 10) // 2


def signed(n: int) -> str:
    return f"+{n}" if n >= 0 else str(n)
