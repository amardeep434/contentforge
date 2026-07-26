"""Niche ranking.

    score = rpm_usd * log1p(views_per_day) * (0.5 + entrability) / (1 + log1p(competitors))

RPM sets the revenue ceiling; view velocity rewards demand; entrability rewards
niches newcomers still break into; competitor count damps saturation. Both
volume terms are logarithmic because the difference between 10 and 100
competitors matters far more than between 1,000 and 1,090.

The `0.5 +` floor on entrability penalises a mature niche rather than
eliminating it — a high-RPM niche with few new entrants can still be worth
entering.

These weights are a starting hypothesis, not an empirical result. If the first
real report ranks something obviously wrong, suspect this formula before
suspecting the data.
"""

import math
from dataclasses import dataclass

from contentforge.provenance import Fact
from contentforge.research.metrics import NicheMetrics


@dataclass(frozen=True)
class NicheScore:
    niche: str
    geography: str
    score: float
    rpm_usd: Fact
    metrics: NicheMetrics


def score_niche(metrics: NicheMetrics, rpm_usd: Fact, geography: str) -> NicheScore:
    demand = math.log1p(metrics.median_views_per_day.value)
    openness = 0.5 + metrics.entrability.value
    saturation = 1 + math.log1p(metrics.competitor_count.value)
    return NicheScore(
        niche=metrics.niche,
        geography=geography,
        score=rpm_usd.value * demand * openness / saturation,
        rpm_usd=rpm_usd,
        metrics=metrics,
    )


def rank(scores: list[NicheScore]) -> list[NicheScore]:
    """Return a new list ordered best-first. Does not mutate the input."""
    return sorted(scores, key=lambda score: score.score, reverse=True)
