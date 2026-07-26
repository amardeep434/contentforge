"""Check a claimed channel statistic against the API.

Social feeds are full of "this channel did 6M views and earned $30,000". The
view count is checkable in one API call; the earnings almost never are, because
they are typically the poster's own `views x assumed_RPM` arithmetic wearing the
same formatting as measured data.

This module checks what can be checked and refuses to imply anything about the
rest.
"""

from dataclasses import dataclass

from contentforge.errors import MissingDataError
from contentforge.provenance import Fact
from contentforge.providers.quota import QuotaLedger
from contentforge.providers.youtube_api import YouTubeClient

# A claim within this relative distance of the real figure counts as verified.
# Social posts are screenshots taken days earlier, so exact equality is the
# wrong bar; a channel also keeps growing after the post.
CLAIM_TOLERANCE = 0.05


@dataclass(frozen=True)
class ChannelFacts:
    channel_id: str
    title: str
    subscribers: Fact
    view_count: Fact
    video_count: Fact
    published_at: Fact

    @property
    def views_per_video(self) -> float:
        videos = self.video_count.value
        return self.view_count.value / videos if videos else 0.0


@dataclass(frozen=True)
class ClaimCheck:
    channel: ChannelFacts
    claimed_views: int | None
    view_error: float | None
    verdict: str
    implied_earnings_usd: float | None
    note: str


def _verdict(claimed: int | None, actual: int) -> tuple[str, float | None]:
    if claimed is None:
        return "no view claim to check", None
    error = (actual - claimed) / claimed
    if abs(error) <= CLAIM_TOLERANCE:
        return "VERIFIED", error
    if actual > claimed:
        return "UNDERSTATED (channel grew, or claim was conservative)", error
    return "OVERSTATED", error


def check_claim(
    client: YouTubeClient,
    handle: str,
    ledger: QuotaLedger,
    claimed_views: int | None = None,
    assumed_rpm: float | None = None,
) -> tuple[ClaimCheck, QuotaLedger]:
    """Resolve a channel by handle and compare it against a claimed view count.

    `assumed_rpm` yields an *implied* earnings figure. It is explicitly not a
    measurement — YouTube exposes revenue only to the channel owner — and the
    returned note says so.
    """
    facts, charged = fetch_channel(client, handle, ledger)
    verdict, error = _verdict(claimed_views, facts.view_count.value)

    implied = None
    note = "Earnings are not observable from the API; nothing here verifies revenue."
    if assumed_rpm is not None:
        implied = facts.view_count.value * assumed_rpm / 1000
        note = (
            f"${implied:,.0f} is views x an assumed ${assumed_rpm:.2f} RPM, not a "
            "measurement. Real RPM varies several-fold by niche and geography."
        )

    return (
        ClaimCheck(
            channel=facts,
            claimed_views=claimed_views,
            view_error=error,
            verdict=verdict,
            implied_earnings_usd=implied,
            note=note,
        ),
        charged,
    )


def fetch_channel(
    client: YouTubeClient, handle: str, ledger: QuotaLedger
) -> tuple[ChannelFacts, QuotaLedger]:
    """Look up one channel by @handle. Costs 1 quota unit.

    Handle lookup rather than search: `channels.list` costs 1 unit against
    `search.list`'s 100, and returns the exact channel rather than a guess.
    """
    body, charged = client.channel_by_handle(handle.lstrip("@"), ledger)
    return body, charged


def format_check(check: ClaimCheck) -> str:
    """Render a check as a short human-readable block."""
    facts = check.channel
    lines = [
        f"{facts.title}  (@{facts.channel_id})",
        f"  views        {facts.view_count.value:,}",
        f"  subscribers  {facts.subscribers.value:,}",
        f"  videos       {facts.video_count.value:,}"
        f"   ({facts.views_per_video:,.0f} views/video)",
        f"  created      {facts.published_at.value.date().isoformat()}",
    ]
    if check.claimed_views is not None:
        lines.append(
            f"  claimed      {check.claimed_views:,}"
            f"   -> {check.verdict} ({check.view_error:+.1%})"
        )
    if check.implied_earnings_usd is not None:
        lines.append(f"  implied      ${check.implied_earnings_usd:,.0f}")
    lines.append(f"  note         {check.note}")
    return "\n".join(lines)
