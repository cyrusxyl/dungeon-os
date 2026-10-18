"""The id rules of the DM's files: actors, places, sites, maps."""

import re

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*(#\d+)?$")  # a slug, or an actor of a kind: goblin#2
ID_RULE = "use lower-case letters, digits, '-' or '_'"
