"""Shared campaign-directory resolution for the canon and character CLIs."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CAMPAIGNS_DIR = REPO_ROOT / "game" / "campaigns"


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
