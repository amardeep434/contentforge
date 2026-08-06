"""Leads must not lose their history when the run directory is deleted."""

from datetime import datetime, timezone

import pytest

from contentforge.research.leads import Lead
from contentforge.research.seen import (
    LOOKUP_FAILED,
    NO_CHANNEL,
    UNREAD,
    VERIFIED,
    from_lead,
    load_seen,
    mark,
    save_seen,
    summarise_seen,
    unsettled,
    upsert_seen,
)

DAY1 = datetime(2026, 7, 30, tzinfo=timezone.utc)
DAY2 = datetime(2026, 8, 20, tzinfo=timezone.utc)


def lead(permalink="p1", claim="made $5,000", money=("$5,000",), img_handles=()):
    return Lead(
        author="poster",
        permalink=permalink,
        posted_on="04/25/25",
        claim=claim,
        money_mentioned=money,
        handles_from_text=(),
        image_paths=("a.jpg",),
        reply_image_paths=(),
        handles_from_images=img_handles,
    )


def test_a_fresh_lead_starts_unread():
    assert from_lead(lead(), DAY1).outcome == UNREAD


def test_a_lead_whose_images_were_read_is_not_unread():
    assert from_lead(lead(img_handles=("chan",)), DAY1).outcome == NO_CHANNEL


def test_regathering_does_not_erase_that_someone_already_read_it():
    # The whole point: run 2 sees the same post and must not reset it to unread.
    first = [from_lead(lead(), DAY1)]
    read = mark(first, "p1", NO_CHANNEL)
    merged = upsert_seen(read, [from_lead(lead(), DAY2)])
    assert merged[0].outcome == NO_CHANNEL
    assert merged[0].first_seen == "2026-07-30"
    assert merged[0].last_seen == "2026-08-20"


def test_an_unread_post_can_still_be_updated_by_a_later_run():
    first = [from_lead(lead(), DAY1)]
    merged = upsert_seen(first, [from_lead(lead(img_handles=("chan",)), DAY2)])
    assert merged[0].outcome == NO_CHANNEL


def test_verified_outcome_survives_regathering():
    rows = mark([from_lead(lead(), DAY1)], "p1", VERIFIED, handles="eonatlas")
    merged = upsert_seen(rows, [from_lead(lead(), DAY2)])
    assert merged[0].outcome == VERIFIED
    assert merged[0].handles == "eonatlas"


def test_mark_rejects_an_unknown_outcome():
    with pytest.raises(ValueError):
        mark([from_lead(lead(), DAY1)], "p1", "probably-fine")


def test_mark_does_not_mutate_its_input():
    rows = [from_lead(lead(), DAY1)]
    snapshot = list(rows)
    mark(rows, "p1", VERIFIED)
    assert rows == snapshot


def test_unsettled_lists_only_what_still_needs_reading():
    rows = [from_lead(lead("p1"), DAY1), from_lead(lead("p2"), DAY1)]
    rows = mark(rows, "p1", VERIFIED)
    assert [r.permalink for r in unsettled(rows)] == ["p2"]


def test_round_trip_through_csv(tmp_path):
    path = tmp_path / "seen.csv"
    rows = [from_lead(lead("p1"), DAY1), from_lead(lead("p2"), DAY1)]
    save_seen(path, rows)
    assert {r.permalink for r in load_seen(path)} == {"p1", "p2"}


def test_missing_file_loads_as_empty(tmp_path):
    assert load_seen(tmp_path / "nope.csv") == []


def test_summary_keeps_the_uncheckable_denominator():
    # C-039 is a ratio; it is only meaningful if the posts that named nothing
    # are still counted after their run directory is gone.
    rows = [
        mark([from_lead(lead("p1"), DAY1)], "p1", NO_CHANNEL)[0],
        mark([from_lead(lead("p2"), DAY1)], "p2", VERIFIED)[0],
        from_lead(lead("p3", claim="no numbers", money=()), DAY1),
    ]
    text = summarise_seen(rows)
    assert "3 posts seen across all runs" in text
    assert "posts claiming money: 2, of which 1 named no channel (50% uncheckable)" in text
