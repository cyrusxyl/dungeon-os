"""arena command - show or preview the board of the running fight"""

import sys

from dnd_cli import combat
from dnd_cli.commands.show_cmd import preview_path, run_stage
from stage import arena


def _arena_of(campaign_dir, arena_id: str | None):
    """(id, arena): the one named, else the arena of the running fight."""
    if arena_id is None:
        arena_id = (combat.load_state(campaign_dir).get("active_encounter") or {}).get("arena")
        if arena_id is None:
            raise arena.ArenaError("no fight on a board is running. Start one with: uv run dnd-cli encounter start goblin:3 --arena")
    a = arena.load(campaign_dir, arena_id)
    if a is None:
        raise arena.ArenaError(f"no arena {arena_id!r}.")
    return arena_id, a


def execute_show(campaign, arena_id: str | None) -> int:
    def go(campaign_dir):
        arena_id_, a = _arena_of(campaign_dir, arena_id)
        spec = a["spec"]
        print(f"{arena_id_}: {a['w']} x {a['h']}, layout {spec['layout']}, light {spec['light']}, "
              f"source {spec['source']}{' ' + spec['source_id'] if spec['source_id'] else ''}.")
        for p in a["props"]:
            b = arena.board_of(p["kind"])
            print(f"  {p['id']} at ({p['x']}, {p['y']}): cover {b['cover']}" + (", blocks sight" if b["blocks_sight"] else "")
                  + (", blocks movement" if b["blocks_move"] else ""))
        for it in a["items"]:
            print(f"  item {it['name']} at ({it['x']}, {it['y']})")
        for cid, u in a["units"].items():
            print(f"  {cid} at ({u['x']}, {u['y']})" + (f" [{a['control'][cid]}]" if cid in a.get("control", {}) else ""))
        return 0
    return run_stage(campaign, go, arena.ArenaError)


def execute_preview(campaign, arena_id: str | None) -> int:
    def go(campaign_dir):
        arena_id_, a = _arena_of(campaign_dir, arena_id)
        out = preview_path(campaign_dir, f"arena-{arena_id_}")
        arena.render_full(a).save(out)
        print(f"Preview (the whole arena, DM only): {out}", file=sys.stdout)
        return 0
    return run_stage(campaign, go, arena.ArenaError)
