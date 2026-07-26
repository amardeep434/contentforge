import pytest

from contentforge.errors import MissingDataError, QuotaExceededError
from contentforge.providers.quota import QuotaLedger
from contentforge.providers.youtube_api import YouTubeClient
from contentforge.research.discover import discover_niche

RESPONSES = {
    "index funds": {
        "etag": "e1",
        "items": [
            {"id": {"channelId": "UC_a"}, "snippet": {"title": "A"}},
            {"id": {"channelId": "UC_b"}, "snippet": {"title": "B"}},
        ],
    },
    "etf investing": {
        "etag": "e2",
        "items": [
            {"id": {"channelId": "UC_b"}, "snippet": {"title": "B"}},
            {"id": {"channelId": "UC_c"}, "snippet": {"title": "C"}},
        ],
    },
}


def routing_transport(endpoint, params):
    return RESPONSES[params["q"]]


def test_discover_dedupes_channels_across_queries():
    client = YouTubeClient(api_key="k", transport=routing_transport)
    candidate, _ledger = discover_niche(
        client, "finance", ["index funds", "etf investing"], QuotaLedger()
    )
    assert set(candidate.channel_ids) == {"UC_a", "UC_b", "UC_c"}
    assert candidate.niche == "finance"
    assert candidate.queries == ("index funds", "etf investing")


def test_dedupe_preserves_first_seen_order():
    client = YouTubeClient(api_key="k", transport=routing_transport)
    candidate, _ledger = discover_niche(
        client, "finance", ["index funds", "etf investing"], QuotaLedger()
    )
    assert candidate.channel_ids == ("UC_a", "UC_b", "UC_c")


def test_discover_charges_100_units_per_query():
    client = YouTubeClient(api_key="k", transport=routing_transport)
    _candidate, ledger = discover_niche(
        client, "finance", ["index funds", "etf investing"], QuotaLedger()
    )
    assert ledger.spent == 200


def test_discover_stops_cleanly_when_quota_runs_out():
    client = YouTubeClient(api_key="k", transport=routing_transport)
    with pytest.raises(QuotaExceededError):
        discover_niche(
            client,
            "finance",
            ["index funds", "etf investing"],
            QuotaLedger(daily_limit=150),
        )


def test_empty_query_list_raises_rather_than_returning_provenanceless_candidate():
    client = YouTubeClient(api_key="k", transport=routing_transport)
    with pytest.raises(MissingDataError):
        discover_niche(client, "finance", [], QuotaLedger())


def test_candidate_carries_provenance():
    client = YouTubeClient(api_key="k", transport=routing_transport)
    candidate, _ledger = discover_niche(client, "finance", ["index funds"], QuotaLedger())
    assert candidate.provenance.response_id == "e1"
