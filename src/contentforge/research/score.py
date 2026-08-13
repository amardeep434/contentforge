"""Trajectory-based niche ranking.

    score = rpm_usd * breakout_rate * median_lift * membership_factor

RPM sets the revenue ceiling. Breakout rate answers "do newcomers here actually
break through" — the question revision 1's competitor count was trying and
failing to ask, because that metric was bounded by our own sample size. Median
lift answers "when they do, how big is the jump". Membership factor encodes
whether first revenue is reachable at 500 subscribers or only at 1,000.

These weights are a hypothesis. If a run ranks something obviously wrong,
suspect this formula before the data.
"""

from dataclasses import dataclass
from statistics import median

from contentforge.errors import MissingDataError
from contentforge.provenance import Fact, require_facts
from contentforge.research.niches import Niche

# Made for Kids removes Super Thanks and Memberships, so the Tier 1 revenue path
# (500 subscribers) does not exist there. Halving is a judgement call, not a
# measurement — if kids ranks oddly, this constant is the first suspect.
MEMBERSHIP_PENALTY = 0.5


@dataclass(frozen=True)
class NicheScore:
    niche: str
    geography: str
    score: float
    rpm_usd: Fact
    sampled_channels: int
    breakout_count: int
    breakout_rate: float
    median_lift: float
    membership_factor: float

    def __post_init__(self) -> None:
        require_facts(self, "rpm_usd")


def score_niche(niche: Niche, trajectories: list, rpm_usd: Fact) -> NicheScore:
    if not trajectories:
        raise MissingDataError(
            f"no trajectories for niche {niche.name!r}; refusing to score an empty sample"
        )

    lifts = [
        trajectory.inflection.lift
        for trajectory in trajectories
        if trajectory.inflection is not None
    ]
    breakout_rate = len(lifts) / len(trajectories)
    median_lift = median(lifts) if lifts else 0.0
    membership_factor = 1.0 if niche.memberships_available else MEMBERSHIP_PENALTY

    return NicheScore(
        niche=niche.name,
        geography=niche.geography,
        score=rpm_usd.value * breakout_rate * median_lift * membership_factor,
        rpm_usd=rpm_usd,
        sampled_channels=len(trajectories),
        breakout_count=len(lifts),
        breakout_rate=breakout_rate,
        median_lift=median_lift,
        membership_factor=membership_factor,
    )


def rank(scores: list[NicheScore]) -> list[NicheScore]:
    """Return a new list ordered best-first. Does not mutate the input."""
    return sorted(scores, key=lambda score: score.score, reverse=True)
