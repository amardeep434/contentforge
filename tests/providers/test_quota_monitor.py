from datetime import datetime, timezone

from contentforge.providers.quota_monitor import (
    QuotaReading,
    from_local_ledger,
    read_authoritative_usage,
    unknown,
)

NOW = datetime(2026, 7, 26, 20, 0, tzinfo=timezone.utc)


def test_unknown_is_not_zero():
    """The bug this module exists to prevent: a ledger reported 2 units spent
    because it had only witnessed 2, and the caller read that as authoritative
    while the real project counter was exhausted."""
    reading = unknown("no credentials")
    assert reading.spent is None
    assert reading.spent != 0
    assert reading.is_known is False
    assert reading.remaining is None


def test_unknown_is_never_authoritative():
    assert unknown("whatever").authoritative is False


def test_local_ledger_reading_is_explicitly_not_authoritative():
    reading = from_local_ledger(spent=2, limit=10_000)
    assert reading.spent == 2
    assert reading.authoritative is False
    assert "invisible" in reading.detail


def test_local_reading_computes_remaining():
    assert from_local_ledger(spent=2_000, limit=10_000).remaining == 8_000


def test_remaining_never_goes_negative():
    assert from_local_ledger(spent=12_000, limit=10_000).remaining == 0


def test_missing_project_id_reads_unknown_not_zero(monkeypatch):
    monkeypatch.delenv("YOUTUBE_PROJECT_ID", raising=False)
    reading = read_authoritative_usage(NOW)
    assert reading.is_known is False
    assert "YOUTUBE_PROJECT_ID" in reading.detail


def test_missing_credentials_reads_unknown_not_zero(monkeypatch):
    monkeypatch.setenv("YOUTUBE_PROJECT_ID", "proj-123")
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    reading = read_authoritative_usage(NOW)
    assert reading.is_known is False
    assert reading.spent is None
    assert "monitoring.viewer" in reading.detail


def test_a_known_reading_reports_its_source():
    reading = QuotaReading(
        source="cloud-monitoring", authoritative=True,
        spent=9_800, limit=10_000, detail="test",
    )
    assert reading.is_known
    assert reading.remaining == 200
    assert reading.authoritative
