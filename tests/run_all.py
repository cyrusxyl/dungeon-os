"""Run every test suite, one after the other, and say which failed.

    .venv/bin/python tests/run_all.py            # the suites (about 15 seconds)
    .venv/bin/python tests/run_all.py --visual   # also the browser checks (need Chrome)
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    suites = sorted(HERE.glob("test_*.py"))
    if "--visual" in sys.argv:
        suites += [HERE / "visual_roll_window.py", HERE / "visual_arena.py"]
    failed = []
    for suite in suites:
        start = time.time()
        run = subprocess.run([sys.executable, str(suite)], cwd=HERE.parent, capture_output=True, text=True)
        last = (run.stdout.strip().splitlines() or ["(no output)"])[-1]
        print(f"{'ok  ' if run.returncode == 0 else 'FAIL'} {suite.name:28} {last}  [{time.time() - start:.1f}s]")
        if run.returncode:
            failed.append(suite.name)
            print("\n".join(f"     {line}" for line in (run.stdout + run.stderr).splitlines() if "FAIL" in line or "Error" in line)[:3000])
    print(f"\n{len(suites) - len(failed)} of {len(suites)} suites passed" + (f"; failed: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
