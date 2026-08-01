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


def test_new_rows_carry_no_human_opinion():
    row = from_profile(profile(), DAY1)
    assert row.status == ""
    assert row.first_seen == row.last_checked == "2026-07-30"


def test_a_verdict_is_recorded_separately_from_human_status():
    from contentforge.research.analytics import judge

    verdict = judge({**profile(), "channel_id": "UC1"})
    row = from_profile(profile(), DAY1, verdict=verdict)
    assert row.verdict == "exemplar"
    assert "views per subscriber" in row.verdict_reason
    assert row.status == ""          # untouched by machinery
    assert row.standing == "exemplar"


def test_a_human_status_overrides_the_machine_verdict():
    from dataclasses import replace
    from contentforge.research.analytics import judge

    row = from_profile(profile(), DAY1, verdict=judge({**profile(), "channel_id": "UC1"}))
    overridden = replace(row, status="rejected", notes="reads scraped charts")
    assert overridden.verdict == "exemplar"   # machine call preserved for audit
    assert overridden.standing == "rejected"  # human wins


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


def test_summary_counts_by_verdict():
    from contentforge.research.analytics import judge

    rows = [
        from_profile(
            profile(channel_id="UC1", subs=16_700, median=112_000),
            DAY1,
            verdict=judge({**profile(channel_id="UC1", subs=16_700), "n": 12}),
        ),
        from_profile(
            profile(channel_id="UC2", subs=1_030_000, median=2_000_000),
            DAY1,
            verdict=judge(profile(channel_id="UC2", subs=1_030_000, median=2_000_000)),
        ),
    ]
    text = summarise(rows)
    assert "2 channels tracked, 2 judged" in text
    assert "exemplar (consistent and reachable): 1" in text
    assert "watch (strong but too large):        1" in text


def test_a_human_rejection_removes_it_from_the_exemplar_list():
    from dataclasses import replace
    from contentforge.research.analytics import judge

    row = from_profile(profile(), DAY1, verdict=judge({**profile(), "channel_id": "UC1"}))
    assert "exemplars:" in summarise([row])
    assert "exemplars:" not in summarise([replace(row, status="rejected")])


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


def test_human_status_must_use_the_verdict_vocabulary():
    # "watching" instead of "watch" silently dropped channels from every
    # summary, because `standing` returned a value nothing counted.
    import pytest

    from contentforge.research.potentials import validate_status

    assert validate_status("watch") == "watch"
    assert validate_status("") == ""
    with pytest.raises(ValueError):
        validate_status("watching")
    with pytest.raises(ValueError):
        validate_status("rejected")


def test_standing_and_verdict_share_one_vocabulary():
    from contentforge.research.analytics import EXEMPLAR, REJECT, WATCH
    from contentforge.research.potentials import VALID_STATUS

    assert {EXEMPLAR, WATCH, REJECT} <= set(VALID_STATUS)
