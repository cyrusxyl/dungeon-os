"""site command - set a building or dungeon the party walks through on the visual stage"""

import os
import random
import sys

from dnd_cli.campaign import CampaignError
from dnd_cli.commands.show_cmd import _stage_campaign_dir
from stage import actors, beat, crawl, maps
from stage.assets import AssetError


def _run(campaign, fn) -> int:
    try:
        return fn(_stage_campaign_dir(campaign))
    except (CampaignError, OSError, KeyError, crawl.SiteError, AssetError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _summary(site_id: str, site: dict) -> str:
    spec = site["spec"]
    lines = [f"{site_id}: {crawl.site_name(site_id, site)}, theme {spec['theme']}, size {spec['size']}, "
             f"danger {spec['danger']}, {len(site['areas'])} areas, {len(site['entered'])} entered."]
    for pid, p in site["pois"].items():
        where = next((q["where"] for q in spec["pois"] if q["id"] == pid), "?")
        lines.append(f"  {pid}@{where}:{p['icon']} {'found' if p['found'] else 'not found'}")
    return "\n".join(lines)


def execute_set(campaign, site_id: str, tokens: list[str], change: bool = False) -> int:
    def go(campaign_dir):
        if not crawl.ID_RE.match(site_id):
            raise crawl.SiteError(f"site id {site_id!r}: use lower-case letters, digits, '-' or '_'.")
        current = crawl.load(campaign_dir, site_id)
        if current is not None and not change:
            print(f"{site_id!r} is already set; the stage uses it as saved:\n{_summary(site_id, current)}\n"
                  "Nothing changed. Add --change to add points of interest or change name= or danger=.", file=sys.stderr)
            return 1
        is_actor = lambda kind: actors.load(campaign_dir, kind) is not None  # noqa: E731
        spec, new = crawl.build(tokens, current["spec"] if current else None, is_actor)
        if current is None:
            spec["pois"] = new
            site = crawl.generate(spec)
        else:
            site = current
            # New points go where the party has not looked yet.
            crawl.add_pois(site, new, random.Random(), unseen_only=True)
            spec["pois"] = spec["pois"] + new
            site["spec"] = spec
        crawl.save(campaign_dir, site_id, site)
        if os.environ.get("DUNGEON_STAGE_LOG"):
            beat.append(campaign_dir, [{"type": "site_updated", "site": site_id}])
        print("Saved. " + _summary(site_id, site))
        print(f"Show it with the beat line: @explore {site_id}")
        if current is None and (tip := maps.hint(campaign_dir, site_id)):
            print(tip)
        return 0
    return _run(campaign, go)


def execute_show(campaign, site_id: str) -> int:
    def go(campaign_dir):
        site = crawl.load(campaign_dir, site_id)
        if site is None:
            print(f"No site {site_id!r} yet. Set one with: uv run dnd-cli site set {site_id} theme=...", file=sys.stderr)
            return 1
        print(_summary(site_id, site))
        return 0
    return _run(campaign, go)


def execute_preview(campaign, site_id: str) -> int:
    def go(campaign_dir):
        site = crawl.load(campaign_dir, site_id)
        if site is None:
            print(f"No site {site_id!r} yet.", file=sys.stderr)
            return 1
        out = campaign_dir / ".cache" / "stage" / f"site-{site_id}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        crawl.render_full(site).save(out)
        print(f"Preview (the whole layout, DM only): {out}")
        return 0
    return _run(campaign, go)


def execute_options() -> int:
    print("Usage: uv run dnd-cli site set <site-id> theme=<t> [size=small|medium|large] [danger=none|low|mid|high] "
          "[name=<Name_With_Underscores>] poi=<id>@<where>[:<icon>] ...")
    print("Themes: " + ", ".join(f"{k} ({v['style']})" for k, v in crawl.themes().items()))
    print("Where (by walking distance from the entrance): " + ", ".join(crawl.WHERE))
    print("Icons: " + ", ".join(crawl.data()["icons"]) + "; or an actor kind (goblin, skeleton, a saved actor id).")
    print("Beat lines: @explore <site-id> | @explore <site-id> <poi-id> | @explore <site-id> entrance")
    return 0
