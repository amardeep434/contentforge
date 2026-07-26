"""Per-niche metrics.

Definitions are fixed here so scoring is reproducible across runs:

- competitor_count      channels in the candidate set with >= 10,000 subscribers
- median_views_per_day  median of view_count / channel_age_days across the set
- entrability           fraction of the set younger than 18 months; high means
                        newcomers are still gaining traction

Median rather than mean for velocity: one breakout channel would otherwise drag
a dead niche's average up and make it look healthy.
"""

from dataclasses import dataclass
from datetime import datetime
from statistics import median

from contentforge.errors import MissingDataError
from contentforge.provenance import Fact
from contentforge.research.discover import NicheCandidate

SUBSCRIBER_THRESHOLD = 10_000
YOUNG_CHANNEL_DAYS = 548  # 18 months


@dataclass(frozen=True)
class NicheMetrics:
    niche: str
    competitor_count: Fact
    median_views_per_day: Fact
    entrability: Fact


def compute_metrics(
    candidate: NicheCandidate, channel_stats: list, now: datetime
) -> NicheMetrics:
    if not channel_stats:
        raise MissingDataError(
            f"no channel statistics for niche {candidate.niche!r}; "
            "refusing to score an empty set"
        )

    provenance = channel_stats[0].subscribers.provenance

    competitors = sum(
        1 for row in channel_stats if row.subscribers.value >= SUBSCRIBER_THRESHOLD
    )

    views_per_day: list[float] = []
    young = 0
    for row in channel_stats:
        # Clamp to >=1: a channel created today (or with a clock-skewed future
        # date) must not divide by zero or produce negative velocity.
        age_days = max((now - row.published_at.value).days, 1)
        views_per_day.append(row.view_count.value / age_days)
        if age_days <= YOUNG_CHANNEL_DAYS:
            young += 1

    return NicheMetrics(
        niche=candidate.niche,
        competitor_count=Fact(competitors, provenance),
        median_views_per_day=Fact(median(views_per_day), provenance),
        entrability=Fact(young / len(channel_stats), provenance),
    )
