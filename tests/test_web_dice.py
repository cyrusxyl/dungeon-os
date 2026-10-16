"""The web dice and the throw sim (stage/web/check/dice.check.ts), run with Node.

Run from the repo root:  .venv/bin/python tests/test_web_dice.py
Needs Node 22.6 or newer (it runs the TypeScript file as it is). It skips (exit 0) without Node or with an older one.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

CHECK = Path(__file__).resolve().parents[1] / "stage" / "web" / "check" / "dice.check.ts"


def main() -> int:
    node = shutil.which("node")
    if not node:
        print("skipped: Node is not installed")
        return 0
    version = subprocess.run([node, "-v"], capture_output=True, text=True).stdout.strip().lstrip("v").split(".")
    major, minor = (int(x) for x in version[:2]) if len(version) >= 2 and version[0].isdigit() and version[1].isdigit() else (0, 0)
    if (major, minor) < (22, 6):
        print(f"skipped: Node {'.'.join(version)} cannot run TypeScript files (22.6 or newer can)")
        return 0
    flags = ["--experimental-strip-types"] if (major, minor) < (22, 18) else []  # 22.18 and newer strip types by default
    run = subprocess.run([node, *flags, str(CHECK)], capture_output=True, text=True)
    print(run.stdout + run.stderr)
    return run.returncode


if __name__ == "__main__":
    sys.exit(main())
