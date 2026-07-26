import json
from datetime import date, datetime, timedelta, timezone

import pytest

from contentforge.errors import QuotaExceededError
from contentforge.providers.quota import QuotaLedger
from contentforge.providers.quota_store import (
    estimate_run_cost,
    load_ledger,
    quota_date,
    require_headroom,
    save_ledger,
)


def test_quota_date_uses_pacific_not_utc():
    """23:00 UTC is still the previous day in Pacific; treating it as today
    would silently double the apparent budget."""
    utc_late = datetime(2026, 7, 26, 23, 0, tzinfo=timezone.utc)
    assert quota_date(utc_late) == date(2026, 7, 26)

    utc_early = datetime(2026, 7, 27, 3, 0, tzinfo=timezone.utc)  # 20:00 Pacific on the 26th
    assert quota_date(utc_early) == date(2026, 7, 26)

    utc_after_reset = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)  # 01:00 Pacific on the 27th
    assert quota_date(utc_after_reset) == date(2026, 7, 27)


def test_quota_date_rejects_naive_datetime():
    with pytest.raises(ValueError):
        quota_date(datetime(2026, 7, 26, 23, 0))


def test_missing_file_yields_a_fresh_ledger(tmp_path):
    ledger = load_ledger(tmp_path / "none.json", datetime.now(timezone.utc))
    assert ledger.spent == 0


def test_spend_survives_a_round_trip(tmp_path):
    now = datetime(2026, 7, 26, 20, 0, tzinfo=timezone.utc)
    path = tmp_path / "quota.json"
    save_ledger(path, QuotaLedger(spent=4920), now)
    assert load_ledger(path, now).spent == 4920


def test_ledger_resets_when_the_pacific_date_rolls_over(tmp_path):
    path = tmp_path / "quota.json"
    before = datetime(2026, 7, 27, 3, 0, tzinfo=timezone.utc)   # 26th Pacific
    after = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)    # 27th Pacific
    save_ledger(path, QuotaLedger(spent=9000), before)
    assert load_ledger(path, before).spent == 9000
    assert load_ledger(path, after).spent == 0, "API counter resets at Pacific midnight"


def test_save_is_atomic_and_leaves_no_temp_file(tmp_path):
    path = tmp_path / "quota.json"
    save_ledger(path, QuotaLedger(spent=10), datetime.now(timezone.utc))
    assert path.exists()
    assert not list(tmp_path.glob("*.tmp"))
    assert json.loads(path.read_text())["spent"] == 10


def test_estimate_matches_the_observed_run():
    """The real 15-niche US run at 75 channels reported 4,920 units.
    Two searches fired per niche because the target filled after 100 candidates."""
    estimated = estimate_run_cost(niches=15, queries_per_niche=2, channels_per_niche=75)
    assert abs(estimated - 4920) / 4920 < 0.15, f"estimate {estimated} vs observed 4920"


def test_headroom_check_passes_when_affordable():
    require_headroom(QuotaLedger(spent=1000), estimated=5000)


def test_headroom_check_refuses_before_spending_anything():
    with pytest.raises(QuotaExceededError) as excinfo:
        require_headroom(QuotaLedger(spent=8000), estimated=5000)
    assert "2,000 remain" in str(excinfo.value)


def test_headroom_error_names_the_reset_zone():
    with pytest.raises(QuotaExceededError) as excinfo:
        require_headroom(QuotaLedger(spent=9999), estimated=500)
    assert "America/Los_Angeles" in str(excinfo.value)


# --- concurrency ------------------------------------------------------------

def test_concurrent_runs_do_not_lose_spend(tmp_path):
    """Two runs each spending 100 must total 200, not 100.

    Overwriting with an absolute figure loses the loser's spend, and the loss
    is always an undercount - the one direction that breaks the guarantee.
    """
    now = datetime(2026, 7, 26, 20, 0, tzinfo=timezone.utc)
    path = tmp_path / "quota.json"

    a = load_ledger(path, now); a_start = a.spent
    b = load_ledger(path, now); b_start = b.spent      # both read 0
    a = QuotaLedger(spent=a_start + 100)
    b = QuotaLedger(spent=b_start + 100)

    save_ledger(path, a, now, a_start)
    save_ledger(path, b, now, b_start)

    assert load_ledger(path, now).spent == 200


def test_a_stale_writer_cannot_move_the_ledger_backwards(tmp_path):
    """The bug observed live: a stalled run finished and wrote its old state
    over a newer value, dropping the ledger from 1 back to 0."""
    now = datetime(2026, 7, 26, 20, 0, tzinfo=timezone.utc)
    path = tmp_path / "quota.json"

    stale = load_ledger(path, now); stale_start = stale.spent   # reads 0
    save_ledger(path, QuotaLedger(spent=5), now, 0)             # a later run records 5
    save_ledger(path, stale, now, stale_start)                  # stale writer lands late

    assert load_ledger(path, now).spent == 5, "must not regress"


def test_delta_is_never_negative(tmp_path):
    now = datetime(2026, 7, 26, 20, 0, tzinfo=timezone.utc)
    path = tmp_path / "quota.json"
    save_ledger(path, QuotaLedger(spent=10), now, 0)
    save_ledger(path, QuotaLedger(spent=3), now, 99)   # nonsense start
    assert load_ledger(path, now).spent == 10


def test_corrupt_ledger_file_is_treated_as_empty(tmp_path):
    now = datetime(2026, 7, 26, 20, 0, tzinfo=timezone.utc)
    path = tmp_path / "quota.json"
    path.write_text("{not json")
    assert load_ledger(path, now).spent == 0
