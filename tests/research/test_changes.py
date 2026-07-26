from datetime import datetime, timedelta, timezone

from contentforge.research.changes import describe_change
from contentforge.research.trajectory import ChannelTrajectory, Inflection, VideoPoint

NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)


def point(days_ago, vel, duration, title):
    return VideoPoint(
        video_id=f"v{days_ago}",
        published_at=NOW - timedelta(days=days_ago),
        velocity=vel,
        duration_seconds=duration,
        title=title,
    )


def trajectory_with_inflection():
    before = [point(400 - n * 10, 1.0, 600, "short title") for n in range(5)]
    after = [
        point(200 - n * 5, 50.0, 60, "a much longer clickable title here")
        for n in range(5)
    ]
    points = tuple(sorted(before + after, key=lambda p: p.published_at))
    return ChannelTrajectory(
        channel_id="UC_a",
        points=points,
        inflection=Inflection(
            index=5,
            published_at=points[5].published_at,
            before_median=1.0,
            after_median=50.0,
            lift=50.0,
        ),
    )


def test_detects_duration_shift():
    profile = describe_change(trajectory_with_inflection())
    assert profile.duration_before == 600
    assert profile.duration_after == 60


def test_detects_title_length_shift():
    profile = describe_change(trajectory_with_inflection())
    assert profile.title_words_before == 2
    assert profile.title_words_after == 6


def test_detects_cadence_shift():
    profile = describe_change(trajectory_with_inflection())
    assert profile.cadence_days_before == 10
    assert profile.cadence_days_after == 5


def test_returns_none_without_an_inflection():
    points = tuple(point(100 - n, 1.0, 600, "t") for n in range(10))
    traj = ChannelTrajectory(channel_id="UC_a", points=points, inflection=None)
    assert describe_change(traj) is None


def test_single_video_side_reports_zero_cadence_rather_than_crashing():
    points = tuple(
        [point(400, 1.0, 600, "t")] + [point(100 - n * 5, 50.0, 60, "t t") for n in range(9)]
    )
    traj = ChannelTrajectory(
        channel_id="UC_a",
        points=points,
        inflection=Inflection(
            index=1,
            published_at=points[1].published_at,
            before_median=1.0,
            after_median=50.0,
            lift=50.0,
        ),
    )
    assert describe_change(traj).cadence_days_before == 0
