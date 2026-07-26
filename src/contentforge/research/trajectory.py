"""Per-channel view trajectories and breakout detection.

The API exposes no historical channel data, so the climb is reconstructed from
per-video observations. Every comparison uses views-per-day-since-publish: raw
view counts are confounded by age, and comparing them directly makes every old
video look successful.
"""

from dataclasses import dataclass
from datetime import datetime
from statistics import median

from contentforge.errors import MissingDataError

MIN_SIDE_VIDEOS = 5
MIN_LIFT = 3.0


@dataclass(frozen=True)
class VideoPoint:
    video_id: str
    published_at: datetime
    velocity: float
    duration_seconds: int
    title: str


@dataclass(frozen=True)
class Inflection:
    index: int
    published_at: datetime
    before_median: float
    after_median: float
    lift: float


@dataclass(frozen=True)
class ChannelTrajectory:
    channel_id: str
    points: tuple[VideoPoint, ...]
    inflection: Inflection | None


def velocity(view_count: int, published_at: datetime, now: datetime) -> float:
    """Views per day since publish.

    Age clamps to one day minimum so a video published today, or one carrying a
    clock-skewed future date, neither divides by zero nor goes negative.
    """
    age_days = max((now - published_at).days, 1)
    return view_count / age_days


def build_trajectory(channel_id: str, videos: list, now: datetime) -> ChannelTrajectory:
    """Order a channel's videos by date and locate its breakout, if any.

    The inflection is the split maximising the ratio of median velocity after it
    to median velocity before it, requiring at least MIN_SIDE_VIDEOS on each
    side. A channel whose best split falls below MIN_LIFT has not broken out and
    reports None — which is a finding, not a failure, since non-breakouts are
    the control group.
    """
    required = MIN_SIDE_VIDEOS * 2
    if len(videos) < required:
        raise MissingDataError(
            f"channel {channel_id!r} has {len(videos)} videos; "
            f"need at least {required} to detect an inflection"
        )

    points = tuple(
        sorted(
            (
                VideoPoint(
                    video_id=video.video_id,
                    published_at=video.published_at.value,
                    velocity=velocity(
                        video.view_count.value, video.published_at.value, now
                    ),
                    duration_seconds=video.duration_seconds.value,
                    title=video.title,
                )
                for video in videos
            ),
            key=lambda point: point.published_at,
        )
    )

    best: Inflection | None = None
    for index in range(MIN_SIDE_VIDEOS, len(points) - MIN_SIDE_VIDEOS + 1):
        before = median(point.velocity for point in points[:index])
        after = median(point.velocity for point in points[index:])
        if before <= 0:
            continue
        lift = after / before
        if best is None or lift > best.lift:
            best = Inflection(
                index=index,
                published_at=points[index].published_at,
                before_median=before,
                after_median=after,
                lift=lift,
            )

    if best is not None and best.lift < MIN_LIFT:
        best = None

    return ChannelTrajectory(channel_id=channel_id, points=points, inflection=best)
