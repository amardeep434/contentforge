"""Authoritative quota usage, read from Cloud Monitoring.

The local ledger only knows what it personally witnessed. It was added partway
through a day of heavy API use and confidently reported "2 units spent" while
the real project counter was exhausted — because everything spent before it
existed was invisible to it. Local accounting is a forecast, not a fact.

Cloud Monitoring reports what the project actually consumed:

    metric.type   = "serviceruntime.googleapis.com/quota/allocation/usage"
    resource.type = "consumer_quota"

**The invariant this module exists to enforce: unknown must never read as zero.**
When usage cannot be established, `spent` is None and `authoritative` is False,
and callers must treat that as "I do not know" rather than "nothing spent". A
zero that means "no data" is exactly how the pre-flight check waved through a
run that had no quota left.

Authentication is Application Default Credentials — a service account with
`roles/monitoring.viewer`. An API key is not sufficient; Monitoring is
IAM-scoped. Set GOOGLE_APPLICATION_CREDENTIALS and YOUTUBE_PROJECT_ID to enable
it. Without them the pipeline still runs, but on the local forecast, and says so.
"""

import os
from dataclasses import dataclass
from datetime import datetime, timedelta

QUOTA_METRIC = "serviceruntime.googleapis.com/quota/allocation/usage"
SERVICE = "youtube.googleapis.com"

# The two limits YouTube enforces independently. Exhausting either one fails
# requests while the other still shows headroom — which is how a run died
# mid-flight with the unit pool reading almost untouched.
DEFAULT_QUOTA_ID = "defaultPerDayPerProject"
SEARCH_QUOTA_ID = "SearchQueriesPerDay"


@dataclass(frozen=True)
class QuotaReading:
    """What is known about consumption, and how much to trust it."""

    source: str
    authoritative: bool
    spent: int | None
    limit: int | None
    detail: str

    @property
    def is_known(self) -> bool:
        return self.spent is not None

    @property
    def remaining(self) -> int | None:
        if self.spent is None or self.limit is None:
            return None
        return max(self.limit - self.spent, 0)


def unknown(detail: str) -> QuotaReading:
    """A reading that carries no number. Never substitute zero for this."""
    return QuotaReading(
        source="none", authoritative=False, spent=None, limit=None, detail=detail
    )


def from_local_ledger(spent: int, limit: int) -> QuotaReading:
    return QuotaReading(
        source="local-ledger",
        authoritative=False,
        spent=spent,
        limit=limit,
        detail=(
            "Local forecast: counts only calls this pipeline made and recorded. "
            "Spend from other clients, other machines, or before the ledger "
            "existed is invisible to it."
        ),
    )


def _build_monitoring_client():
    """Return a Monitoring client, or None when credentials are absent."""
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return None
    try:
        from googleapiclient.discovery import build

        return build("monitoring", "v3", cache_discovery=False)
    except Exception:
        # Missing library or unusable credentials: report unknown, never zero.
        return None


def read_authoritative_usage(
    now: datetime, quota_id: str = DEFAULT_QUOTA_ID
) -> QuotaReading:
    """Consumption for one YouTube quota metric, straight from Cloud Monitoring.

    Returns an `unknown` reading rather than raising, so a monitoring outage
    degrades the pipeline to its local forecast instead of stopping it — but
    the caller can always tell which it got.
    """
    project = os.environ.get("YOUTUBE_PROJECT_ID")
    if not project:
        return unknown("YOUTUBE_PROJECT_ID is not set")

    client = _build_monitoring_client()
    if client is None:
        return unknown(
            "GOOGLE_APPLICATION_CREDENTIALS not set, or the Monitoring client "
            "could not be built. Monitoring needs a service account with "
            "roles/monitoring.viewer; an API key will not work."
        )

    window_start = now - timedelta(hours=25)
    query = (
        f'metric.type="{QUOTA_METRIC}" AND '
        f'resource.type="consumer_quota" AND '
        f'resource.label."service"="{SERVICE}" AND '
        f'metric.label."quota_metric"=monitoring.regex.full_match(".*{quota_id}.*")'
    )
    try:
        response = (
            client.projects()
            .timeSeries()
            .list(
                name=f"projects/{project}",
                filter=query,
                **{
                    "interval_startTime": window_start.isoformat(),
                    "interval_endTime": now.isoformat(),
                },
            )
            .execute()
        )
    except Exception as error:
        return unknown(f"Monitoring query failed: {type(error).__name__}")

    series = response.get("timeSeries") or []
    if not series:
        return unknown(
            f"Monitoring returned no series for {quota_id}. Usage may genuinely "
            "be zero, or the metric may not be exported yet — this is reported "
            "as unknown rather than guessed."
        )

    points = series[0].get("points") or []
    if not points:
        return unknown(f"Monitoring series for {quota_id} carried no points")

    value = points[0].get("value", {})
    spent = int(value.get("int64Value") or value.get("doubleValue") or 0)
    return QuotaReading(
        source="cloud-monitoring",
        authoritative=True,
        spent=spent,
        limit=None,
        detail=f"Cloud Monitoring, {quota_id}, over the last 25h",
    )
