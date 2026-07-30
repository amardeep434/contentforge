"""The potentials list must not lose human judgement when it refreshes."""

from datetime import datetime, timezone
from pathlib import Path

from contentforge.research.potentials import (
    from_profile,
    load_potentials,
    save_potentials,
    summarise,
    upsert,
)

DAY1 = datetime(2026, 7, 30, tzinfo=timezone.utc)
DAY2 = datetime(2026, 8, 15, tzinfo=timezone.utc)


def profile(channel_id="UC1", handle="chan", median=100_000, subs=10_000, **over):
    base = {
        "channel_id": channel_id,
        "handle": handle,
        "title": "A Channel",
        "subs": subs,
        "n": 12,
        "median": median,
        "mean": 120_000,
        "skew": 1.2,
        "hit_rate": 58.0,
        "min": 900,
        "max": 500_000,
        "repeatable": True,
    }
    base.update(over)
    return base


def test_views_per_sub_is_computed():
    row = from_profile(profile(median=67_000, subs=10_000), DAY1)
    assert row.views_per_sub == 6.7


def test_new_rows_start_as_candidates():
    row = from_profile(profile(), DAY1)
    assert row.status == "candidate"
    assert row.first_seen == row.last_checked == "2026-07-30"


def test_reachable_is_about_inferring_to_a_new_channel():
    assert from_profile(profile(subs=16_700), DAY1).reachable is True
    assert from_profile(profile(subs=1_030_000), DAY1).reachable is False


def test_refresh_updates_measurements(tmp_path):
    first = [from_profile(profile(median=100_000), DAY1)]
    second = [from_profile(profile(median=250_000), DAY2)]
    merged = upsert(first, second)
    assert len(merged) == 1
    assert merged[0].median == 250_000
    assert merged[0].last_checked == "2026-08-15"


def test_refresh_preserves_status_notes_and_first_seen():
    # A human marked this rejected. A later research pass must not silently
    # promote it back to candidate, or the judgement is worthless.
    from dataclasses import replace

    judged = replace(
        from_profile(profile(), DAY1),
        status="rejected",
        notes="reads scraped charts verbatim",
    )
    merged = upsert([judged], [from_profile(profile(median=999_999), DAY2)])
    assert merged[0].status == "rejected"
    assert merged[0].notes == "reads scraped charts verbatim"
    assert merged[0].first_seen == "2026-07-30"
    assert merged[0].median == 999_999  # measurement still refreshed


def test_dedupe_is_by_channel_id_not_handle():
    # Handles get renamed; ids do not. Keying on handle would create a
    # duplicate row for the same channel after a rename.
    original = [from_profile(profile(channel_id="UC1", handle="oldname"), DAY1)]
    renamed = [from_profile(profile(channel_id="UC1", handle="newname"), DAY2)]
    merged = upsert(original, renamed)
    assert len(merged) == 1
    assert merged[0].handle == "newname"


def test_a_genuinely_new_channel_is_appended():
    merged = upsert(
        [from_profile(profile(channel_id="UC1"), DAY1)],
        [from_profile(profile(channel_id="UC2"), DAY2)],
    )
    assert {row.channel_id for row in merged} == {"UC1", "UC2"}


def test_upsert_does_not_mutate_its_inputs():
    existing = [from_profile(profile(median=1), DAY1)]
    snapshot = list(existing)
    upsert(existing, [from_profile(profile(median=2), DAY2)])
    assert existing == snapshot


def test_round_trip_through_csv(tmp_path):
    path = tmp_path / "potentials.csv"
    rows = [
        from_profile(profile(channel_id="UC1", median=5_000), DAY1),
        from_profile(profile(channel_id="UC2", median=90_000), DAY1),
    ]
    save_potentials(path, rows)
    loaded = load_potentials(path)
    assert loaded[0].median == 90_000  # sorted by median, highest first
    assert set(r.channel_id for r in loaded) == {"UC1", "UC2"}
    assert loaded[0].repeatable is True


def test_missing_file_loads_as_empty(tmp_path):
    assert load_potentials(tmp_path / "nope.csv") == []


def test_summary_highlights_reachable_and_repeatable():
    rows = [
        from_profile(profile(channel_id="UC1", subs=16_700, median=112_000), DAY1),
        from_profile(profile(channel_id="UC2", subs=1_030_000), DAY1),
        from_profile(profile(channel_id="UC3", repeatable=False), DAY1),
    ]
    text = summarise(rows)
    assert "3 channels tracked" in text
    assert "repeatable (skew<=3, hit>=40%, n>=8): 2" in text
    assert "of those, reachable (<80k subs):      1" in text


def test_rejected_channels_are_excluded_from_the_summary():
    from dataclasses import replace

    rows = [replace(from_profile(profile(), DAY1), status="rejected")]
    assert "reachable and repeatable" not in summarise(rows)


def test_incoming_duplicates_collapse_to_one_row():
    # Two scans of the same channel arriving in one batch must not create two
    # rows; the later measurement wins.
    merged = upsert(
        [],
        [
            from_profile(profile(channel_id="UC1", median=112_326), DAY1),
            from_profile(profile(channel_id="UC1", median=111_040), DAY2),
        ],
    )
    assert len(merged) == 1
    assert merged[0].median == 111_040


def test_a_missing_handle_is_not_printed_as_one():
    # Scan endpoints return a title but no handle. Rendering "@Art History
    # Explained" invents a handle that does not resolve.
    from dataclasses import replace

    row = replace(from_profile(profile(), DAY1), handle="", title="Art History Explained")
    assert row.label == "Art History Explained"
    assert from_profile(profile(handle="brainosophic"), DAY1).label == "@brainosophic"
