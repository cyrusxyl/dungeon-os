"""JSON files of the stage: read tolerant, write by rename.

The stage server and the DM's CLI both read and write files under
`{campaign}/stage/`, so a writer never leaves a half-written file.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def read_json(path: Path) -> dict | None:
    """The file's JSON object, or None when it is missing or broken."""
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_json(path: Path, obj: dict, indent: int | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f, indent=indent, separators=None if indent else (",", ":"))
        if indent:
            f.write("\n")
    os.replace(tmp, path)
    return path
