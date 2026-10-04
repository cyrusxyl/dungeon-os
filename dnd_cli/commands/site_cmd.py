"""site command - set a building or dungeon the party walks through on the visual stage"""

import random
import sys

from dnd_cli.commands.show_cmd import notify_stage, preview_path, run_stage
from stage import actors, beat, crawl, maps
from stage.assets import AssetError


def _summary(site_id: str, site: dict) -> str:
    spec = site["spec"]
    lines = [f"{site_id}: {crawl.site_name(site_id, site)}, theme {spec['theme']}, size {spec['size']}, "
             f"danger {spec['danger']}, {len(site['areas'])} areas, {len(site['entered'])} entered."]
    for pid, p in site["pois"].items():
        lines.append(f"  {pid}@{p['where']}:{p['icon']} {'found' if p['found'] else 'not found'}")
    return "\n".join(lines)


def execute_set(campaign, site_id: str, tokens: list[str], change: bool = False) -> int:
    def go(campaign_dir):
        if not beat.SLUG_RE.match(site_id):
            raise crawl.SiteError(f"site id {site_id!r}: {beat.ID_RULE}.")
        current = crawl.load(campaign_dir, site_id)
        if current is not None and not change:
            print(f"{site_id!r} is already set; the stage uses it as saved:\n{_summary(site_id, current)}\n"
                  "Nothing changed. Add --change to add points of interest or change name= or danger=.", file=sys.stderr)
            return 1
        is_actor = lambda kind: actors.load(campaign_dir, kind) is not None  # noqa: E731
        if current is None:
            spec, new = crawl.build(tokens, None, is_actor)
            site = crawl.generate(spec, new)
        else:
            site = current
            site["spec"], new = crawl.build(tokens, site["spec"], is_actor, site["pois"])
            # New points go where the party has not looked yet.
            crawl.add_pois(site, new, random.Random())
        crawl.save(campaign_dir, site_id, site)
        notify_stage(campaign_dir, {"type": "site_updated", "site": site_id})
        print("Saved. " + _summary(site_id, site))
        print(f"Show it with the beat line: @explore {site_id}")
        if current is None and (tip := maps.hint(campaign_dir, site_id)):
            print(tip)
        return 0
    return run_stage(campaign, go, crawl.SiteError, AssetError)


def execute_show(campaign, site_id: str) -> int:
    def go(campaign_dir):
        site = crawl.load(campaign_dir, site_id)
        if site is None:
            print(f"No site {site_id!r} yet. Set one with: uv run dnd-cli site set {site_id} theme=...", file=sys.stderr)
            return 1
        print(_summary(site_id, site))
        return 0
    return run_stage(campaign, go, crawl.SiteError, AssetError)


def execute_preview(campaign, site_id: str) -> int:
    def go(campaign_dir):
        site = crawl.load(campaign_dir, site_id)
        if site is None:
            print(f"No site {site_id!r} yet.", file=sys.stderr)
            return 1
        out = preview_path(campaign_dir, f"site-{site_id}")
        crawl.render_full(site).save(out)
        print(f"Preview (the whole layout, DM only): {out}")
        return 0
    return run_stage(campaign, go, crawl.SiteError, AssetError)


def execute_options() -> int:
    print("Usage: uv run dnd-cli site set <site-id> theme=<t> [size=small|medium|large] [danger=none|low|mid|high] "
          "[name=<Name_With_Underscores>] poi=<id>@<where>[:<icon>] ...")
    print("Themes: " + ", ".join(f"{k} ({v['style']})" for k, v in crawl.themes().items()))
    print("Where (by walking distance from the entrance): " + ", ".join(crawl.WHERE))
    print("Icons: " + ", ".join(crawl.data()["icons"]) + "; or an actor kind (goblin, skeleton, a saved actor id).")
    print("Beat lines: @explore <site-id> | @explore <site-id> <poi-id> | @explore <site-id> entrance")
    return 0
