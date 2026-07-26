from datetime import datetime, timezone

import pytest

from contentforge.errors import MissingDataError
from contentforge.providers.youtube_api import ChannelStats
from contentforge.provenance import Fact, Provenance
from contentforge.research.discover import NicheCandidate
from contentforge.research.metrics import compute_metrics

NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)
PROV = Provenance(source_url="https://x", response_id="r", retrieved_at=NOW)

CANDIDATE = NicheCandidate(
    niche="finance", queries=("q",), channel_ids=("UC_a", "UC_b"), provenance=PROV
)


def stats(cid, subs, views, published):
    return ChannelStats(
        channel_id=cid,
        title=cid,
        subscribers=Fact(subs, PROV),
        video_count=Fact(10, PROV),
        view_count=Fact(views, PROV),
        published_at=Fact(published, PROV),
    )


def test_competitor_count_uses_10k_subscriber_threshold():
    rows = [
        stats("UC_a", 120000, 1000, datetime(2025, 7, 26, tzinfo=timezone.utc)),
        stats("UC_b", 500, 1000, datetime(2025, 7, 26, tzinfo=timezone.utc)),
    ]
    assert compute_metrics(CANDIDATE, rows, NOW).competitor_count.value == 1


def test_channel_exactly_at_threshold_counts_as_competitor():
    rows = [stats("UC_a", 10000, 1000, datetime(2025, 7, 26, tzinfo=timezone.utc))]
    assert compute_metrics(CANDIDATE, rows, NOW).competitor_count.value == 1


def test_median_views_per_day_is_hand_computable():
    # UC_a: 3650 views / 365 days = 10.0/day
    # UC_b: 7300 views / 365 days = 20.0/day
    # median of [10.0, 20.0] = 15.0
    rows = [
        stats("UC_a", 20000, 3650, datetime(2025, 7, 26, tzinfo=timezone.utc)),
        stats("UC_b", 20000, 7300, datetime(2025, 7, 26, tzinfo=timezone.utc)),
    ]
    metrics = compute_metrics(CANDIDATE, rows, NOW)
    assert metrics.median_views_per_day.value == pytest.approx(15.0)


def test_entrability_is_fraction_younger_than_18_months():
    rows = [
        stats("UC_a", 20000, 1000, datetime(2026, 3, 1, tzinfo=timezone.utc)),
        stats("UC_b", 20000, 1000, datetime(2019, 1, 1, tzinfo=timezone.utc)),
    ]
    assert compute_metrics(CANDIDATE, rows, NOW).entrability.value == pytest.approx(0.5)


def test_empty_channel_set_raises_rather_than_scoring_zero():
    with pytest.raises(MissingDataError):
        compute_metrics(CANDIDATE, [], NOW)


def test_channel_published_today_does_not_divide_by_zero():
    rows = [stats("UC_a", 20000, 100, NOW)]
    metrics = compute_metrics(CANDIDATE, rows, NOW)
    assert metrics.median_views_per_day.value == pytest.approx(100.0)


def test_future_published_date_does_not_produce_negative_velocity():
    future = datetime(2027, 1, 1, tzinfo=timezone.utc)
    rows = [stats("UC_a", 20000, 100, future)]
    metrics = compute_metrics(CANDIDATE, rows, NOW)
    assert metrics.median_views_per_day.value > 0


def test_metrics_carry_provenance():
    rows = [stats("UC_a", 20000, 1000, datetime(2025, 7, 26, tzinfo=timezone.utc))]
    metrics = compute_metrics(CANDIDATE, rows, NOW)
    assert metrics.competitor_count.provenance.response_id == "r"
    assert metrics.median_views_per_day.provenance.response_id == "r"
    assert metrics.entrability.provenance.response_id == "r"
