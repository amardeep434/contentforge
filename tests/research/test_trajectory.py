from datetime import datetime, timedelta, timezone

import pytest

from contentforge.errors import MissingDataError
from contentforge.providers.youtube_api import VideoRecord
from contentforge.provenance import Fact, Provenance
from contentforge.research.trajectory import MIN_LIFT, build_trajectory, velocity

NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)
PROV = Provenance(source_url="https://x", response_id="r", retrieved_at=NOW)


def video(vid, days_ago, views, duration=600, title="t"):
    published = NOW - timedelta(days=days_ago)
    return VideoRecord(
        video_id=vid,
        channel_id="UC_a",
        title=title,
        published_at=Fact(published, PROV),
        view_count=Fact(views, PROV),
        duration_seconds=Fact(duration, PROV),
        provenance=PROV,
    )


def test_velocity_is_views_per_day():
    assert velocity(1000, NOW - timedelta(days=100), NOW) == pytest.approx(10.0)


def test_velocity_clamps_age_to_one_day_minimum():
    assert velocity(50, NOW, NOW) == pytest.approx(50.0)


def test_velocity_treats_future_dates_as_one_day_old():
    assert velocity(50, NOW + timedelta(days=5), NOW) == pytest.approx(50.0)


def test_trajectory_orders_points_oldest_first():
    videos = [video("v2", 10, 100), video("v1", 200, 100)] + [
        video(f"f{n}", 300 - n, 10) for n in range(8)
    ]
    traj = build_trajectory("UC_a", videos, NOW)
    assert traj.points[0].published_at < traj.points[-1].published_at


def test_detects_inflection_when_velocity_jumps():
    videos = [video(f"old{n}", 400 - n, 400 - n) for n in range(6)]
    videos += [video(f"new{n}", 50 - n, (50 - n) * 100) for n in range(6)]
    traj = build_trajectory("UC_a", videos, NOW)
    assert traj.inflection is not None
    assert traj.inflection.lift >= MIN_LIFT
    assert traj.inflection.after_median > traj.inflection.before_median


def test_no_inflection_on_a_flat_channel():
    videos = [video(f"v{n}", 400 - n * 20, (400 - n * 20) * 10) for n in range(12)]
    traj = build_trajectory("UC_a", videos, NOW)
    assert traj.inflection is None, "steady channel must not report a breakout"


def test_no_inflection_when_the_jump_is_too_early_to_split_on():
    videos = [video(f"v{n}", 400 - n * 20, 10) for n in range(2)]
    videos += [video(f"w{n}", 300 - n * 20, 100000) for n in range(10)]
    traj = build_trajectory("UC_a", videos, NOW)
    assert traj.inflection is None


def test_declining_channel_reports_no_inflection():
    videos = [video(f"old{n}", 700 - n * 10, (700 - n * 10) * 50) for n in range(6)]
    videos += [video(f"new{n}", 60 - n * 5, 40) for n in range(6)]
    traj = build_trajectory("UC_a", videos, NOW)
    assert traj.inflection is None, "a collapse must never read as a breakout"


def test_too_few_videos_raises():
    with pytest.raises(MissingDataError):
        build_trajectory("UC_a", [video("v1", 10, 10)], NOW)


def test_points_carry_duration_and_title_for_change_attribution():
    videos = [video(f"v{n}", 400 - n * 20, 100, duration=333, title="a b c") for n in range(12)]
    traj = build_trajectory("UC_a", videos, NOW)
    assert traj.points[0].duration_seconds == 333
    assert traj.points[0].title == "a b c"
