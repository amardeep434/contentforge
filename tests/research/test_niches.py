from datetime import datetime, timezone
from pathlib import Path

import pytest

from contentforge.errors import MissingDataError
from contentforge.provenance import Provenance
from contentforge.research.niches import Niche, load_niches, rpm_midpoint_usd

TABLE = Path(__file__).parent.parent.parent / "data" / "niches.csv"


def test_table_covers_at_least_twelve_niches():
    names = {key[0] for key in load_niches(TABLE)}
    assert len(names) >= 12, f"only {len(names)} niches; the point of v2 is breadth"


def test_every_row_is_sourced():
    for niche in load_niches(TABLE).values():
        assert niche.provenance.source_url.startswith("http")
        assert niche.provenance.retrieved_at.tzinfo is not None


def test_every_row_has_at_least_three_seed_queries():
    for key, niche in load_niches(TABLE).items():
        assert len(niche.seed_queries) >= 3, f"{key} has too few seed queries"


def test_seed_queries_are_long_tail_not_head_terms():
    """Head terms return the same incumbents for every niche, which is what
    defeated revision 1. Multi-word queries are the crude proxy for long-tail."""
    for key, niche in load_niches(TABLE).items():
        for query in niche.seed_queries:
            assert len(query.split()) >= 3, f"{key}: {query!r} is a head term"


def test_kids_is_flagged_membership_restricted_with_contextual_only_rpm():
    kids = load_niches(TABLE)[("kids", "US")]
    assert kids.memberships_available is False
    assert kids.rpm_high <= 5, "Made for Kids serves contextual ads only"


def test_finance_allows_memberships():
    assert load_niches(TABLE)[("finance", "US")].memberships_available is True


def test_rpm_midpoint_converts_inr():
    india = load_niches(TABLE)[("finance", "IN")]
    assert rpm_midpoint_usd(india).value == pytest.approx(
        (india.rpm_low + india.rpm_high) / 2 / 88.0
    )


def test_rpm_midpoint_leaves_usd_alone():
    finance = load_niches(TABLE)[("finance", "US")]
    assert rpm_midpoint_usd(finance).value == pytest.approx(
        (finance.rpm_low + finance.rpm_high) / 2
    )


def test_us_finance_outranks_india_finance_after_conversion():
    table = load_niches(TABLE)
    assert (
        rpm_midpoint_usd(table[("finance", "US")]).value
        > rpm_midpoint_usd(table[("finance", "IN")]).value
    )


def test_unsupported_currency_raises():
    bogus = Niche(
        name="x", geography="EU", rpm_low=1, rpm_high=2, currency="EUR",
        memberships_available=True, seed_queries=("a b c",),
        provenance=Provenance("https://x", "r", datetime.now(timezone.utc)),
    )
    with pytest.raises(MissingDataError):
        rpm_midpoint_usd(bogus)


def test_empty_table_raises(tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text(
        "niche,geography,rpm_low,rpm_high,currency,memberships_available,"
        "seed_queries,source_url,retrieved_at\n"
    )
    with pytest.raises(MissingDataError):
        load_niches(empty)
