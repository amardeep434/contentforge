"""Analytics must be pure, ordered, and explain itself."""

from contentforge.research.analytics import (
    CRITERIA_VERSION,
    EXEMPLAR,
    REJECT,
    WATCH,
    judge,
    judge_all,
    tally,
)


def measurement(**over):
    base = {
        "channel_id": "UC1",
        "handle": "chan",
        "subs": 16_700,
        "n": 12,
        "median": 112_000,
        "mean": 120_000,
        "skew": 1.1,
        "hit_rate": 62.0,
    }
    base.update(over)
    return base


def test_repeatable_and_small_is_an_exemplar():
    verdict = judge(measurement())
    assert verdict.status == EXEMPLAR
    assert "6.7 views per subscriber" in verdict.reason


def test_repeatable_but_large_is_watch_not_exemplar():
    # Its numbers come partly from an existing base, so they say nothing about
    # a channel starting from zero.
    verdict = judge(measurement(subs=1_030_000))
    assert verdict.status == WATCH
    assert "cannot be extrapolated" in verdict.reason


def test_high_skew_is_rejected_as_lottery_shaped():
    verdict = judge(measurement(skew=5.7))
    assert verdict.status == REJECT
    assert "5.7x the median" in verdict.reason


def test_low_hit_rate_is_rejected():
    verdict = judge(measurement(hit_rate=21.0))
    assert verdict.status == REJECT
    assert "21% is below 40%" in verdict.reason


def test_too_few_videos_is_rejected_before_anything_else():
    # Sample size is checked first: reporting "lottery-shaped" for a channel
    # with 3 videos would name the wrong problem.
    verdict = judge(measurement(n=3, skew=99.0, hit_rate=0.0))
    assert verdict.status == REJECT
    assert "only 3 long-form videos" in verdict.reason


def test_the_first_failure_is_the_reported_one():
    verdict = judge(measurement(skew=9.0, hit_rate=2.0))
    assert "9.0x the median" in verdict.reason
    assert "hit-rate" not in verdict.reason


def test_every_verdict_records_the_ruleset_that_produced_it():
    assert judge(measurement()).criteria_version == CRITERIA_VERSION


def test_judging_is_pure_and_does_not_touch_its_input():
    data = measurement()
    snapshot = dict(data)
    judge(data)
    assert data == snapshot


def test_boundaries_are_inclusive_where_documented():
    assert judge(measurement(n=8)).status != REJECT           # n >= 8 passes
    assert judge(measurement(skew=3.0)).status != REJECT      # skew <= 3 passes
    assert judge(measurement(hit_rate=40.0)).status != REJECT # hit >= 40 passes
    assert judge(measurement(subs=80_000)).status == EXEMPLAR # <= 80k reachable


def test_tally_counts_each_status():
    verdicts = judge_all(
        [
            measurement(channel_id="UC1"),
            measurement(channel_id="UC2", subs=900_000),
            measurement(channel_id="UC3", skew=8.0),
        ]
    )
    assert tally(verdicts) == {EXEMPLAR: 1, WATCH: 1, REJECT: 1}
