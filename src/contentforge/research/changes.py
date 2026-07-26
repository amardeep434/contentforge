"""What differed before and after a channel's inflection.

Within-channel comparison only. Comparing breakout channels to each other
invites survivorship bias: "posted consistently, then went viral" describes the
winners and equally describes the many who did the same and sank. Holding the
creator fixed cancels channel-level confounds.

This describes what changed and that it coincided with the inflection. It never
claims causation — retention, traffic source and thumbnail click-through are not
exposed for other people's channels.
"""

from dataclasses import dataclass
from statistics import median

from contentforge.research.trajectory import ChannelTrajectory, VideoPoint


@dataclass(frozen=True)
class ChangeProfile:
    duration_before: int
    duration_after: int
    cadence_days_before: int
    cadence_days_after: int
    title_words_before: float
    title_words_after: float


def _median_gap_days(points: tuple[VideoPoint, ...]) -> int:
    """Median days between consecutive uploads. Zero when there is only one."""
    if len(points) < 2:
        return 0
    ordered = sorted(points, key=lambda point: point.published_at)
    gaps = [
        (later.published_at - earlier.published_at).days
        for earlier, later in zip(ordered, ordered[1:])
    ]
    return int(median(gaps))


def describe_change(trajectory: ChannelTrajectory) -> ChangeProfile | None:
    """Diff a channel's pre-inflection videos against its post-inflection ones.

    Returns None when the channel never broke out — there is nothing to compare.
    """
    if trajectory.inflection is None:
        return None

    before = trajectory.points[: trajectory.inflection.index]
    after = trajectory.points[trajectory.inflection.index :]

    return ChangeProfile(
        duration_before=int(median(point.duration_seconds for point in before)),
        duration_after=int(median(point.duration_seconds for point in after)),
        cadence_days_before=_median_gap_days(before),
        cadence_days_after=_median_gap_days(after),
        title_words_before=median(len(point.title.split()) for point in before),
        title_words_after=median(len(point.title.split()) for point in after),
    )
