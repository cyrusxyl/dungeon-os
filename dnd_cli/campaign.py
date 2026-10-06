"""Shared campaign-directory resolution for the canon and character CLIs."""

import json
import re
import shutil
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GAME_DIR = REPO_ROOT / "game"
CAMPAIGNS_DIR = GAME_DIR / "campaigns"
ACTIVE_PATH = CAMPAIGNS_DIR / "active.json"


class CampaignError(Exception):
    """Base error for anything wrong with a campaign path or its files."""


def resolve_campaign_dir(campaign: str) -> Path:
    """Turn a campaign name or path into a real campaign directory.

    Accepts a bare slug ("baldurs-gate"), a path relative to
    game/campaigns/, or an absolute path. Raises CampaignError if the
    result does not exist.
    """
    candidate = Path(campaign)
    if candidate.is_absolute():
        campaign_dir = candidate
    else:
        # Strip a leading "campaigns/" or "game/campaigns/" if the caller
        # pasted a path instead of a bare slug.
        parts = candidate.parts
        if parts[:2] == ("game", "campaigns"):
            campaign_dir = REPO_ROOT / candidate
        elif parts[:1] == ("campaigns",):
            campaign_dir = REPO_ROOT / "game" / candidate
        else:
            campaign_dir = CAMPAIGNS_DIR / candidate

    if not campaign_dir.is_dir():
        raise CampaignError(f"No campaign directory at {campaign_dir}")
    return campaign_dir


def active_campaign_slug() -> str:
    """Slug of the campaign that campaigns/active.json points at."""
    data = json.loads(ACTIVE_PATH.read_text())
    return Path(data["active_campaign_path"]).name


def set_active_campaign(slug: str) -> None:
    """Point campaigns/active.json at `slug` (a campaign directory name)."""
    ACTIVE_PATH.write_text(
        json.dumps(
            {
                "active_campaign_path": f"campaigns/{slug}",
                "last_updated": date.today().isoformat(),
            },
            indent=2,
        )
        + "\n"
    )


def slugify(name: str) -> str:
    """Turn a campaign name into a directory-safe slug."""
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


def list_campaigns() -> list[tuple[str, str]]:
    """(slug, display name) for every real campaign, template excluded, sorted."""
    out: list[tuple[str, str]] = []
    if not CAMPAIGNS_DIR.is_dir():
        return out
    for path in sorted(CAMPAIGNS_DIR.iterdir()):
        if not path.is_dir() or path.name == "template":
            continue
        if not (path / "config.json").exists():
            continue
        out.append((path.name, campaign_display_name(path)))
    return out


def campaign_display_name(campaign_dir: Path) -> str:
    """The campaign's `config.json` name, or its directory name as a fallback."""
    try:
        name = json.loads((campaign_dir / "config.json").read_text()).get(
            "campaign_name"
        )
    except (json.JSONDecodeError, OSError):
        name = None
    return name or campaign_dir.name


def delete_campaign(slug: str) -> None:
    """Remove a campaign folder (its saves are inside it). Only a bare slug, never the template."""
    if slug != Path(slug).name or slug in ("", ".", "..", "template"):
        raise CampaignError("Bad campaign name.")
    campaign_dir = CAMPAIGNS_DIR / slug
    if not (campaign_dir / "config.json").is_file():
        raise CampaignError("No such campaign.")
    shutil.rmtree(campaign_dir)
    try:
        if active_campaign_slug() == slug:
            ACTIVE_PATH.unlink()
    except (OSError, ValueError, KeyError):
        pass


def create_campaign(name: str, pitch: str = "", party: str = "create") -> str:
    """Scaffold a new campaign directory from the template. Returns its slug.

    `pitch` is the player's free text; `party` says who makes the characters:
    "create" (the player) or "premade" (the DM, from the pitch).
    """
    pitch = pitch.strip()
    if party not in ("create", "premade"):
        raise CampaignError("party is 'create' or 'premade'.")
    if party == "premade" and not pitch:
        raise CampaignError("The DM needs a pitch to make the characters from.")
    slug = slugify(name)
    if not slug:
        raise CampaignError("The name needs at least one letter or digit.")

    template_dir = CAMPAIGNS_DIR / "template"
    dest = CAMPAIGNS_DIR / slug
    if dest.exists():
        raise CampaignError(f"A campaign called '{slug}' already exists.")
    if not template_dir.is_dir():
        raise CampaignError(f"No template campaign at {template_dir}")

    shutil.copytree(template_dir, dest)

    config_path = dest / "config.json"
    config = json.loads(config_path.read_text())
    config["campaign_name"] = name
    config["created"] = date.today().isoformat()
    config["pitch"] = pitch
    config["party"] = party
    config_path.write_text(json.dumps(config, indent=2) + "\n")

    canon_path = dest / "canon.json"
    if canon_path.exists():
        canon = json.loads(canon_path.read_text())
        canon["campaign_id"] = slug
        canon_path.write_text(json.dumps(canon, indent=2) + "\n")

    return slug
