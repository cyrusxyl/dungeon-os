"""One dependency direction: core <- dnd_cli rules <- {dnd_cli.commands, stage}.

Read the imports of every module (function-local ones too) and check the direction.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (importer file, imported package) pairs that are allowed on purpose. Say why.
ALLOWED: set[tuple[str, str]] = set()


def imported(path: Path) -> set[str]:
    """The dotted names this file imports. `from a import b` gives `a` and `a.b`."""
    out = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.add(node.module)
            out |= {f"{node.module}.{a.name}" for a in node.names}
    return out


def under(name: str, package: str) -> bool:
    return name == package or name.startswith(package + ".")


def rule_files(package: str) -> list[Path]:
    skip = (ROOT / "dnd_cli" / "commands", ROOT / "dnd_cli" / "__main__.py")
    return [p for p in sorted((ROOT / package).rglob("*.py")) if not any(p == s or s in p.parents for s in skip)]


def main() -> int:
    # (package, what it must not import)
    rules = [("core", ("dnd_cli", "stage")), ("dnd_cli", ("stage", "dnd_cli.commands")), ("stage", ("dnd_cli.commands",))]
    bad = []
    for package, banned in rules:
        for path in rule_files(package):
            rel = str(path.relative_to(ROOT))
            for name in sorted(imported(path)):
                for b in banned:
                    if under(name, b) and (rel, b) not in ALLOWED:
                        bad.append(f"{rel} imports {name} ({package} must not import {b})")
    for line in bad:
        print("  FAIL", line)
    print(f"{'FAIL' if bad else 'ok'}: {len(bad)} layer violations")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
