from pathlib import Path

import pytest

from contentforge.errors import MissingDataError
from contentforge.research.rpm_table import load_rpm_table, rpm_midpoint_usd

TABLE = Path(__file__).parent.parent.parent / "data" / "rpm_table.csv"


def test_every_row_has_a_source_url_and_tz_aware_date():
    table = load_rpm_table(TABLE)
    assert table, "rpm table must not be empty"
    for row in table.values():
        assert row.provenance.source_url.startswith("http")
        assert row.provenance.retrieved_at.tzinfo is not None


def test_lookup_returns_midpoint_as_fact():
    table = load_rpm_table(TABLE)
    fact = rpm_midpoint_usd(table, "finance", "IN")
    assert fact.value > 0
    assert fact.provenance.source_url.startswith("http")


def test_inr_midpoint_is_hand_computable():
    # finance/IN is 80-250 INR, midpoint 165, at 88 INR/USD = 1.875 USD
    table = load_rpm_table(TABLE)
    fact = rpm_midpoint_usd(table, "finance", "IN")
    assert fact.value == pytest.approx(165 / 88.0)


def test_usd_rows_are_not_converted():
    # finance/US is 10-25 USD, midpoint 17.5
    table = load_rpm_table(TABLE)
    fact = rpm_midpoint_usd(table, "finance", "US")
    assert fact.value == pytest.approx(17.5)


def test_missing_combination_raises_rather_than_defaulting():
    table = load_rpm_table(TABLE)
    with pytest.raises(MissingDataError):
        rpm_midpoint_usd(table, "underwater basket weaving", "IN")


def test_missing_geography_raises_rather_than_falling_back():
    table = load_rpm_table(TABLE)
    with pytest.raises(MissingDataError):
        rpm_midpoint_usd(table, "finance", "ZZ")


def test_us_finance_rpm_exceeds_india_after_conversion():
    table = load_rpm_table(TABLE)
    india = rpm_midpoint_usd(table, "finance", "IN")
    usa = rpm_midpoint_usd(table, "finance", "US")
    assert usa.value > india.value


def test_unsupported_currency_raises(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text(
        "niche,geography,rpm_low,rpm_high,currency,source_url,retrieved_at\n"
        "finance,EU,1,2,EUR,https://x,2026-07-26\n"
    )
    table = load_rpm_table(bad)
    with pytest.raises(MissingDataError):
        rpm_midpoint_usd(table, "finance", "EU")
