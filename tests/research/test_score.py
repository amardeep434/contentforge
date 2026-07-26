import math
from datetime import datetime, timezone

import pytest

from contentforge.provenance import Fact, Provenance
from contentforge.research.metrics import NicheMetrics
from contentforge.research.score import rank, score_niche

NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)
PROV = Provenance(source_url="https://x", response_id="r", retrieved_at=NOW)


def metrics(niche, competitors, vpd, entrability):
    return NicheMetrics(
        niche=niche,
        competitor_count=Fact(competitors, PROV),
        median_views_per_day=Fact(vpd, PROV),
        entrability=Fact(entrability, PROV),
    )


def test_score_matches_hand_computed_value():
    m = metrics("finance", competitors=4, vpd=100.0, entrability=0.5)
    result = score_niche(m, Fact(2.0, PROV), "US")
    expected = 2.0 * math.log1p(100.0) * (0.5 + 0.5) / (1 + math.log1p(4))
    assert result.score == pytest.approx(expected)


def test_higher_rpm_scores_higher_all_else_equal():
    m = metrics("finance", 4, 100.0, 0.5)
    low = score_niche(m, Fact(1.0, PROV), "IN")
    high = score_niche(m, Fact(4.0, PROV), "US")
    assert high.score > low.score


def test_more_competitors_scores_lower_all_else_equal():
    few = score_niche(metrics("a", 2, 100.0, 0.5), Fact(2.0, PROV), "US")
    many = score_niche(metrics("a", 200, 100.0, 0.5), Fact(2.0, PROV), "US")
    assert few.score > many.score


def test_higher_entrability_scores_higher_all_else_equal():
    closed = score_niche(metrics("a", 4, 100.0, 0.0), Fact(2.0, PROV), "US")
    open_ = score_niche(metrics("a", 4, 100.0, 1.0), Fact(2.0, PROV), "US")
    assert open_.score > closed.score


def test_zero_entrability_still_scores_above_zero():
    result = score_niche(metrics("a", 4, 100.0, 0.0), Fact(2.0, PROV), "US")
    assert result.score > 0, "a mature niche should be penalised, not eliminated"


def test_zero_competitors_does_not_divide_by_zero():
    result = score_niche(metrics("a", 0, 100.0, 1.0), Fact(2.0, PROV), "US")
    assert result.score > 0


def test_rank_orders_descending():
    a = score_niche(metrics("a", 100, 10.0, 0.1), Fact(1.0, PROV), "IN")
    b = score_niche(metrics("b", 2, 500.0, 0.9), Fact(5.0, PROV), "US")
    assert [s.niche for s in rank([a, b])] == ["b", "a"]


def test_rank_does_not_mutate_input():
    a = score_niche(metrics("a", 100, 10.0, 0.1), Fact(1.0, PROV), "IN")
    b = score_niche(metrics("b", 2, 500.0, 0.9), Fact(5.0, PROV), "US")
    original = [a, b]
    rank(original)
    assert original == [a, b]


def test_score_retains_rpm_and_metrics_for_the_report():
    m = metrics("finance", 4, 100.0, 0.5)
    result = score_niche(m, Fact(2.0, PROV), "US")
    assert result.rpm_usd.value == 2.0
    assert result.metrics is m
    assert result.geography == "US"
