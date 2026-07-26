from datetime import datetime, timedelta, timezone

import pytest

from contentforge.errors import MissingDataError
from contentforge.provenance import Fact, Provenance
from contentforge.research.niches import Niche
from contentforge.research.score import MEMBERSHIP_PENALTY, rank, score_niche
from contentforge.research.trajectory import ChannelTrajectory, Inflection, VideoPoint

NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)
PROV = Provenance(source_url="https://x", response_id="r", retrieved_at=NOW)


def a_niche(name="finance", memberships=True):
    return Niche(
        name=name, geography="US", rpm_low=10, rpm_high=20, currency="USD",
        memberships_available=memberships, seed_queries=("a b c",), provenance=PROV,
    )


def traj(channel_id, lift=None):
    points = tuple(
        VideoPoint(f"v{n}", NOW - timedelta(days=100 - n), 1.0, 600, "t")
        for n in range(10)
    )
    inflection = (
        None
        if lift is None
        else Inflection(
            index=5, published_at=points[5].published_at,
            before_median=1.0, after_median=lift, lift=lift,
        )
    )
    return ChannelTrajectory(channel_id=channel_id, points=points, inflection=inflection)


def test_breakout_rate_is_fraction_with_inflection():
    result = score_niche(
        a_niche(), [traj("a", 5.0), traj("b"), traj("c"), traj("d")], Fact(15.0, PROV)
    )
    assert result.breakout_rate == pytest.approx(0.25)
    assert result.breakout_count == 1
    assert result.sampled_channels == 4


def test_median_lift_uses_only_breakout_channels():
    result = score_niche(
        a_niche(), [traj("a", 4.0), traj("b", 10.0), traj("c")], Fact(15.0, PROV)
    )
    assert result.median_lift == pytest.approx(7.0)


def test_score_is_hand_computable():
    result = score_niche(a_niche(), [traj("a", 4.0), traj("b")], Fact(15.0, PROV))
    # rpm 15 * breakout_rate 0.5 * median_lift 4.0 * membership 1.0 = 30
    assert result.score == pytest.approx(30.0)


def test_membership_restriction_penalises_score():
    trajectories = [traj("a", 4.0), traj("b")]
    allowed = score_niche(a_niche(memberships=True), trajectories, Fact(15.0, PROV))
    blocked = score_niche(
        a_niche("kids", memberships=False), trajectories, Fact(15.0, PROV)
    )
    assert blocked.score == pytest.approx(allowed.score * MEMBERSHIP_PENALTY)


def test_niche_with_no_breakouts_scores_zero_not_error():
    result = score_niche(a_niche(), [traj("a"), traj("b")], Fact(15.0, PROV))
    assert result.score == 0.0
    assert result.median_lift == 0.0
    assert result.breakout_rate == 0.0


def test_empty_trajectory_list_raises():
    with pytest.raises(MissingDataError):
        score_niche(a_niche(), [], Fact(15.0, PROV))


def test_rank_orders_descending_without_mutating():
    a = score_niche(a_niche("a"), [traj("x", 2.0), traj("y")], Fact(5.0, PROV))
    b = score_niche(a_niche("b"), [traj("x", 20.0), traj("y", 20.0)], Fact(25.0, PROV))
    original = [a, b]
    assert [s.niche for s in rank(original)] == ["b", "a"]
    assert original == [a, b]


def test_score_retains_sample_size_for_the_report():
    result = score_niche(a_niche(), [traj("a", 4.0), traj("b")], Fact(15.0, PROV))
    assert result.sampled_channels == 2
    assert result.rpm_usd.provenance.source_url == "https://x"
