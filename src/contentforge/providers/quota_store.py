"""Persistent quota accounting across runs.

The YouTube Data API grants 10,000 units per project per day, and the counter
resets at **midnight US/Pacific** — not UTC, and not local time. An in-memory
ledger forgets everything between runs, which means a second run of the day
starts from zero and discovers the real limit only by hitting it mid-flight and
losing the whole run's work.

This module persists the ledger keyed on the Pacific date, so a run can check
its headroom before spending anything.
"""

import fcntl
import json
import os
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from contentforge.errors import QuotaExceededError
from contentforge.providers.quota import UNIT_COSTS, QuotaLedger

# The reset boundary Google uses. Not configurable — it is a property of the API.
QUOTA_RESET_ZONE = ZoneInfo("America/Los_Angeles")


def quota_date(now: datetime) -> date:
    """The Pacific calendar date that `now` falls in.

    A run at 23:00 UTC belongs to the previous Pacific day, and treating it as
    today's would silently double the apparent budget.
    """
    if now.tzinfo is None:
        raise ValueError("quota_date requires a timezone-aware datetime")
    return now.astimezone(QUOTA_RESET_ZONE).date()


@contextmanager
def _locked(path: Path):
    """Hold an exclusive lock on a sidecar file for a read-modify-write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(path.suffix + ".lock")
    handle = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        os.close(handle)


def _read_spent(path: Path, today: str) -> int:
    """Spend recorded on disk for `today`, or 0 if absent or stale."""
    if not path.exists():
        return 0
    try:
        record = json.loads(path.read_text())
    except json.JSONDecodeError:
        return 0
    if record.get("date") != today:
        # Stale file from a previous day: the API counter has already reset.
        return 0
    return int(record.get("spent", 0))


def load_ledger(
    path: Path, now: datetime, daily_limit: int = 10_000
) -> QuotaLedger:
    """Load today's ledger, or a fresh one if the Pacific date has rolled over."""
    with _locked(path):
        return QuotaLedger(
            daily_limit=daily_limit,
            spent=_read_spent(path, quota_date(now).isoformat()),
        )


def save_ledger(
    path: Path, ledger: QuotaLedger, now: datetime, started_at: int = 0
) -> None:
    """Add this run's spend to whatever is on disk, under a lock.

    Overwriting with an absolute figure loses concurrent runs' spend, and the
    loss is always an undercount - the one direction that breaks the guarantee.
    So the delta this run consumed is added to the current on-disk value
    instead, and the whole read-modify-write is serialised.
    """
    today = quota_date(now).isoformat()
    delta = max(ledger.spent - started_at, 0)
    with _locked(path):
        total = _read_spent(path, today) + delta
        payload = {
            "date": today,
            "spent": total,
            "daily_limit": ledger.daily_limit,
            "updated_at": now.isoformat(),
        }
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, indent=2))
        temp.replace(path)


def estimate_run_cost(
    niches: int, queries_per_niche: int, channels_per_niche: int
) -> int:
    """Predicted cost of a research run, from the published per-call prices.

    Per niche: one search per seed query, one channels.list per 50 channels for
    the uploads playlists, then one playlistItems.list and one videos.list per
    channel.
    """
    per_niche = (
        queries_per_niche * UNIT_COSTS["search.list"]
        + -(-channels_per_niche // 50) * UNIT_COSTS["channels.list"]
        + channels_per_niche * UNIT_COSTS["playlistItems.list"]
        + channels_per_niche * UNIT_COSTS["videos.list"]
    )
    return niches * per_niche


def require_headroom(ledger: QuotaLedger, estimated: int) -> None:
    """Refuse a run that cannot finish, before it spends anything.

    Aborting at the start costs nothing. Aborting halfway costs everything spent
    so far and produces no report.
    """
    if estimated > ledger.remaining:
        raise QuotaExceededError(
            f"run needs ~{estimated:,} units but only {ledger.remaining:,} remain "
            f"of {ledger.daily_limit:,} today; quota resets at midnight "
            f"{QUOTA_RESET_ZONE.key}. Reduce --channels-per-niche or wait."
        )
