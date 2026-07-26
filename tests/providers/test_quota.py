import pytest

from contentforge.errors import QuotaExceededError
from contentforge.providers.quota import UNIT_COSTS, QuotaLedger


def test_known_unit_costs():
    assert UNIT_COSTS["search.list"] == 100
    assert UNIT_COSTS["videos.list"] == 1
    assert UNIT_COSTS["channels.list"] == 1
    assert UNIT_COSTS["videos.insert"] == 1600


def test_charge_returns_new_ledger_and_does_not_mutate():
    ledger = QuotaLedger()
    charged = ledger.charge("search.list")
    assert ledger.spent == 0, "original ledger must not mutate"
    assert charged.spent == 100
    assert charged is not ledger


def test_remaining_reflects_spend():
    ledger = QuotaLedger().charge("search.list").charge("videos.list")
    assert ledger.spent == 101
    assert ledger.remaining == 9899


def test_charge_raises_when_budget_would_be_exceeded():
    ledger = QuotaLedger(daily_limit=150).charge("search.list")
    with pytest.raises(QuotaExceededError):
        ledger.charge("search.list")


def test_would_exceed_predicts_without_charging():
    ledger = QuotaLedger(daily_limit=150).charge("search.list")
    assert ledger.would_exceed("search.list") is True
    assert ledger.would_exceed("videos.list") is False
    assert ledger.spent == 100, "would_exceed must not charge"


def test_unknown_endpoint_raises_rather_than_assuming_zero():
    with pytest.raises(KeyError):
        QuotaLedger().charge("mystery.endpoint")


def test_charge_exactly_to_the_limit_is_allowed():
    ledger = QuotaLedger(daily_limit=100).charge("search.list")
    assert ledger.spent == 100
    assert ledger.remaining == 0
