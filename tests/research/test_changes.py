import pytest
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


# --- cadence resolution + aggregate summary ---------------------------------

from contentforge.research.changes import ChangeProfile, summarise_changes


def test_cadence_keeps_sub_day_resolution():
    """Whole-day truncation collapsed every daily-or-faster channel to 0d,
    which made cadence unreadable in the first live run."""
    before = [
        VideoPoint(f"b{n}", NOW - timedelta(days=400, hours=n * 6), 1.0, 600, "t")
        for n in range(5)
    ]
    after = [
        VideoPoint(f"a{n}", NOW - timedelta(days=100, hours=n * 2), 50.0, 60, "t")
        for n in range(5)
    ]
    points = tuple(sorted(before + after, key=lambda p: p.published_at))
    traj = ChannelTrajectory(
        channel_id="UC_a", points=points,
        inflection=Inflection(5, points[5].published_at, 1.0, 50.0, 50.0),
    )
    profile = describe_change(traj)
    assert 0 < profile.cadence_days_before < 1, "6h gaps must not truncate to zero"
    assert 0 < profile.cadence_days_after < 1


def a_profile(dur_before, dur_after, cad_before=5.0, cad_after=5.0, tw_before=8, tw_after=8):
    return ChangeProfile(
        duration_before=dur_before, duration_after=dur_after,
        cadence_days_before=cad_before, cadence_days_after=cad_after,
        title_words_before=tw_before, title_words_after=tw_after,
    )


def test_summary_counts_direction_of_duration_change():
    summary = summarise_changes([
        a_profile(600, 60),    # much shorter
        a_profile(600, 60),    # much shorter
        a_profile(100, 900),   # much longer
        a_profile(300, 305),   # inside the deadband
    ])
    assert summary.channels == 4
    assert summary.duration_shorter == 2
    assert summary.duration_longer == 1
    assert summary.duration_unchanged == 1


def test_summary_deadband_treats_small_moves_as_unchanged():
    summary = summarise_changes([a_profile(100, 105)])
    assert summary.duration_unchanged == 1


def test_summary_median_duration_ratio_is_hand_computable():
    summary = summarise_changes([a_profile(100, 50), a_profile(100, 200)])
    # ratios 0.5 and 2.0, median 1.25
    assert summary.median_duration_ratio == pytest.approx(1.25)


def test_summary_reports_faster_cadence_as_shorter_gap():
    summary = summarise_changes([a_profile(100, 100, cad_before=10.0, cad_after=2.0)])
    assert summary.cadence_faster == 1
    assert summary.cadence_slower == 0


def test_summary_title_word_delta():
    summary = summarise_changes([
        a_profile(100, 100, tw_before=8, tw_after=12),
        a_profile(100, 100, tw_before=8, tw_after=10),
    ])
    assert summary.median_title_word_delta == pytest.approx(3.0)


def test_summary_of_empty_list_is_none_not_zeros():
    """Zeros would imply a measured 'no change'; there is simply nothing here."""
    assert summarise_changes([]) is None
