"""What differed before and after a channel's inflection.

Within-channel comparison only. Comparing breakout channels to each other
invites survivorship bias: "posted consistently, then went viral" describes the
winners and equally describes the many who did the same and sank. Holding the
creator fixed cancels channel-level confounds.

Per-channel profiles are noisy — a single channel shortening its videos means
nothing. `summarise_changes` aggregates across a niche's breakout channels,
where a consistent direction would actually be visible.

All of this describes what changed and that it coincided with the inflection.
It never claims causation: retention, traffic source and thumbnail
click-through are not exposed for other people's channels.
"""

from dataclasses import dataclass
from statistics import median

from contentforge.research.trajectory import ChannelTrajectory, VideoPoint

# Below this relative change a metric counts as "unchanged" rather than moved.
# Without a deadband, noise splits roughly 50/50 and every metric looks mixed.
DIRECTION_DEADBAND = 0.10


@dataclass(frozen=True)
class ChangeProfile:
    duration_before: int
    duration_after: int
    cadence_days_before: float
    cadence_days_after: float
    title_words_before: float
    title_words_after: float


@dataclass(frozen=True)
class ChangeSummary:
    """Aggregate direction of change across one niche's breakout channels."""

    channels: int
    duration_shorter: int
    duration_longer: int
    duration_unchanged: int
    median_duration_ratio: float
    cadence_faster: int
    cadence_slower: int
    cadence_unchanged: int
    median_title_word_delta: float


def _median_gap_days(points: tuple[VideoPoint, ...]) -> float:
    """Median days between consecutive uploads, as a fraction.

    Whole-day truncation collapsed every channel posting more than once a day
    to zero, which made cadence unreadable in the first live run.
    """
    if len(points) < 2:
        return 0.0
    ordered = sorted(points, key=lambda point: point.published_at)
    gaps = [
        (later.published_at - earlier.published_at).total_seconds() / 86400
        for earlier, later in zip(ordered, ordered[1:])
    ]
    return float(median(gaps))


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


def _direction(before: float, after: float) -> str:
    """Classify a change as up, down, or flat within the deadband."""
    if before <= 0:
        return "flat"
    ratio = after / before
    if ratio > 1 + DIRECTION_DEADBAND:
        return "up"
    if ratio < 1 - DIRECTION_DEADBAND:
        return "down"
    return "flat"


def summarise_changes(profiles: list[ChangeProfile]) -> ChangeSummary | None:
    """Aggregate per-channel profiles into a niche-level direction.

    Returns None for an empty list — a niche with no breakouts has nothing to
    summarise, and reporting zeros would imply a measured "no change".
    """
    if not profiles:
        return None

    duration_directions = [
        _direction(profile.duration_before, profile.duration_after)
        for profile in profiles
    ]
    cadence_directions = [
        _direction(profile.cadence_days_before, profile.cadence_days_after)
        for profile in profiles
    ]
    duration_ratios = [
        profile.duration_after / profile.duration_before
        for profile in profiles
        if profile.duration_before > 0
    ]

    return ChangeSummary(
        channels=len(profiles),
        duration_shorter=duration_directions.count("down"),
        duration_longer=duration_directions.count("up"),
        duration_unchanged=duration_directions.count("flat"),
        median_duration_ratio=float(median(duration_ratios)) if duration_ratios else 1.0,
        # A shorter gap between uploads means a faster cadence.
        cadence_faster=cadence_directions.count("down"),
        cadence_slower=cadence_directions.count("up"),
        cadence_unchanged=cadence_directions.count("flat"),
        median_title_word_delta=float(
            median(
                profile.title_words_after - profile.title_words_before
                for profile in profiles
            )
        ),
    )
