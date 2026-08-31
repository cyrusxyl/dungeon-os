"""Player-facing view: a real terminal running the DM, plus a state panel.

This package never writes campaign state. The DM session itself is a real
`claude` process running in an embedded terminal widget (see view/app.py);
the side panel reads only an explicit allowlist of files under a campaign
directory (state.json, characters/*.json). See game/campaigns/<slug>/ for
the files it reads and view/app.py for the allowlist enforcement.
"""
