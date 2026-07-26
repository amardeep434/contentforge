import json
from pathlib import Path

import pytest

from contentforge.errors import MissingDataError
from contentforge.providers.quota import QuotaLedger
from contentforge.providers.youtube_api import YouTubeClient

FIXTURES = Path(__file__).parent.parent / "fixtures" / "youtube"


def fixture_transport(name):
    """A transport that always replies with one recorded response."""
    body = json.loads((FIXTURES / name).read_text())

    def _transport(endpoint, params):
        return body

    return _transport


def test_search_channels_returns_refs_with_provenance():
    client = YouTubeClient(api_key="k", transport=fixture_transport("search_finance.json"))
    refs, _ledger = client.search_channels("personal finance", QuotaLedger())
    assert len(refs) == 2
    assert refs[0].channel_id == "UC_finance_a"
    assert refs[0].title == "Finance A"
    assert refs[0].provenance.source_url.startswith(
        "https://www.googleapis.com/youtube/v3/search"
    )
    assert refs[0].provenance.retrieved_at.tzinfo is not None


def test_search_charges_100_units():
    client = YouTubeClient(api_key="k", transport=fixture_transport("search_finance.json"))
    _refs, ledger = client.search_channels("personal finance", QuotaLedger())
    assert ledger.spent == 100


def test_get_channels_charges_one_unit_per_batch_not_per_id():
    client = YouTubeClient(api_key="k", transport=fixture_transport("channels_batch.json"))
    stats, ledger = client.get_channels(["UC_finance_a", "UC_finance_b"], QuotaLedger())
    assert ledger.spent == 1, "channels.list is billed per call, not per id"
    assert len(stats) == 2


def test_channel_stats_values_are_facts():
    client = YouTubeClient(api_key="k", transport=fixture_transport("channels_batch.json"))
    stats, _ledger = client.get_channels(["UC_finance_a"], QuotaLedger())
    assert stats[0].subscribers.value == 120000
    assert stats[0].view_count.value == 18000000
    assert stats[0].subscribers.provenance.response_id == "chan-resp-1"


def test_published_at_is_parsed_timezone_aware():
    client = YouTubeClient(api_key="k", transport=fixture_transport("channels_batch.json"))
    stats, _ledger = client.get_channels(["UC_finance_a"], QuotaLedger())
    assert stats[0].published_at.value.tzinfo is not None
    assert stats[0].published_at.value.year == 2024


def test_missing_statistics_block_raises_rather_than_defaulting_to_zero():
    def broken_transport(endpoint, params):
        return {
            "etag": "chan-resp-1",
            "items": [
                {
                    "id": "UC_x",
                    "snippet": {"title": "X", "publishedAt": "2020-01-01T00:00:00Z"},
                }
            ],
        }

    client = YouTubeClient(api_key="k", transport=broken_transport)
    with pytest.raises(MissingDataError):
        client.get_channels(["UC_x"], QuotaLedger())


def test_empty_search_results_raise_rather_than_returning_empty():
    def empty_transport(endpoint, params):
        return {"etag": "e", "items": []}

    client = YouTubeClient(api_key="k", transport=empty_transport)
    with pytest.raises(MissingDataError):
        client.search_channels("nonsense query", QuotaLedger())


def test_response_without_etag_raises_because_provenance_is_impossible():
    def etagless_transport(endpoint, params):
        return {"items": [{"id": {"channelId": "UC_a"}, "snippet": {"title": "A"}}]}

    client = YouTubeClient(api_key="k", transport=etagless_transport)
    with pytest.raises(MissingDataError):
        client.search_channels("q", QuotaLedger())


def test_quota_is_charged_before_the_call_so_failures_still_count():
    """A failed call still consumed quota upstream; the ledger must reflect that."""

    def exploding_transport(endpoint, params):
        raise RuntimeError("upstream 500")

    client = YouTubeClient(api_key="k", transport=exploding_transport)
    with pytest.raises(RuntimeError):
        client.search_channels("q", QuotaLedger())


def test_get_channels_batches_ids_in_fifties():
    """channels.list rejects more than 50 ids with HTTP 400 invalidFilters.

    Three seed queries at 25 results each can yield 75 unique channels, so the
    unbatched version failed on the first real run.
    """
    calls = []

    def counting_transport(endpoint, params):
        ids = params["id"].split(",")
        calls.append(len(ids))
        assert len(ids) <= 50, f"sent {len(ids)} ids; API caps at 50"
        return {
            "etag": "batched",
            "items": [
                {
                    "id": cid,
                    "snippet": {"title": cid, "publishedAt": "2025-01-01T00:00:00Z"},
                    "statistics": {
                        "subscriberCount": "1",
                        "videoCount": "1",
                        "viewCount": "1",
                    },
                }
                for cid in ids
            ],
        }

    client = YouTubeClient(api_key="k", transport=counting_transport)
    stats, ledger = client.get_channels([f"UC_{n}" for n in range(120)], QuotaLedger())

    assert calls == [50, 50, 20]
    assert len(stats) == 120
    assert ledger.spent == 3, "one unit per channels.list call"


def test_get_channels_charges_one_unit_for_exactly_fifty():
    def transport(endpoint, params):
        ids = params["id"].split(",")
        return {
            "etag": "e",
            "items": [
                {
                    "id": cid,
                    "snippet": {"title": cid, "publishedAt": "2025-01-01T00:00:00Z"},
                    "statistics": {
                        "subscriberCount": "1",
                        "videoCount": "1",
                        "viewCount": "1",
                    },
                }
                for cid in ids
            ],
        }

    client = YouTubeClient(api_key="k", transport=transport)
    _stats, ledger = client.get_channels([f"UC_{n}" for n in range(50)], QuotaLedger())
    assert ledger.spent == 1


# --- revision 2: video history fetching -------------------------------------

from contentforge.providers.youtube_api import parse_iso8601_duration


def test_parse_iso8601_duration_handles_all_components():
    assert parse_iso8601_duration("PT5M30S") == 330
    assert parse_iso8601_duration("PT1M21S") == 81
    assert parse_iso8601_duration("PT1H2M3S") == 3723
    assert parse_iso8601_duration("PT45S") == 45
    assert parse_iso8601_duration("PT2H") == 7200


def test_parse_iso8601_duration_rejects_garbage():
    with pytest.raises(MissingDataError):
        parse_iso8601_duration("banana")


def test_get_uploads_playlists_maps_channel_to_playlist():
    def transport(endpoint, params):
        return {
            "etag": "cd-1",
            "items": [
                {"id": "UC_a", "contentDetails": {"relatedPlaylists": {"uploads": "UU_a"}}},
                {"id": "UC_b", "contentDetails": {"relatedPlaylists": {"uploads": "UU_b"}}},
            ],
        }

    client = YouTubeClient(api_key="k", transport=transport)
    mapping, ledger = client.get_uploads_playlists(["UC_a", "UC_b"], QuotaLedger())
    assert mapping == {"UC_a": "UU_a", "UC_b": "UU_b"}
    assert ledger.spent == 1


def test_get_uploads_playlists_batches_in_fifties():
    calls = []

    def transport(endpoint, params):
        ids = params["id"].split(",")
        calls.append(len(ids))
        assert len(ids) <= 50
        return {
            "etag": "cd",
            "items": [
                {"id": cid, "contentDetails": {"relatedPlaylists": {"uploads": "UU" + cid}}}
                for cid in ids
            ],
        }

    client = YouTubeClient(api_key="k", transport=transport)
    mapping, ledger = client.get_uploads_playlists(
        [f"UC_{n}" for n in range(120)], QuotaLedger()
    )
    assert calls == [50, 50, 20]
    assert len(mapping) == 120
    assert ledger.spent == 3


def test_get_playlist_video_ids_returns_ids():
    def transport(endpoint, params):
        return {
            "etag": "pl-1",
            "items": [{"contentDetails": {"videoId": f"v{n}"}} for n in range(47)],
        }

    client = YouTubeClient(api_key="k", transport=transport)
    ids, ledger = client.get_playlist_video_ids("UU_a", QuotaLedger())
    assert len(ids) == 47
    assert ids[0] == "v0"
    assert ledger.spent == 1


def test_get_videos_returns_records_with_velocity_inputs():
    def transport(endpoint, params):
        return {
            "etag": "vid-1",
            "items": [
                {
                    "id": "v1",
                    "snippet": {
                        "channelId": "UC_a",
                        "title": "How index funds work",
                        "publishedAt": "2025-01-01T00:00:00Z",
                    },
                    "statistics": {"viewCount": "5000"},
                    "contentDetails": {"duration": "PT8M12S"},
                }
            ],
        }

    client = YouTubeClient(api_key="k", transport=transport)
    videos, ledger = client.get_videos(["v1"], QuotaLedger())
    assert len(videos) == 1
    assert videos[0].view_count.value == 5000
    assert videos[0].duration_seconds.value == 492
    assert videos[0].title == "How index funds work"
    assert videos[0].published_at.value.tzinfo is not None
    assert ledger.spent == 1


def test_get_videos_tolerates_missing_view_count_as_zero_not_error():
    def transport(endpoint, params):
        return {
            "etag": "vid-2",
            "items": [
                {
                    "id": "v1",
                    "snippet": {
                        "channelId": "UC_a",
                        "title": "t",
                        "publishedAt": "2026-07-26T00:00:00Z",
                    },
                    "statistics": {},
                    "contentDetails": {"duration": "PT30S"},
                }
            ],
        }

    client = YouTubeClient(api_key="k", transport=transport)
    videos, _ledger = client.get_videos(["v1"], QuotaLedger())
    assert videos[0].view_count.value == 0


def test_parse_iso8601_duration_accepts_live_stream_p0d():
    """Live streams and upcoming premieres report P0D - a real zero, not an error."""
    assert parse_iso8601_duration("P0D") == 0
    assert parse_iso8601_duration("P1D") == 86400


def test_parse_iso8601_duration_still_rejects_empty_and_garbage():
    for bad in ("", "banana", "5M30S"):
        with pytest.raises(MissingDataError):
            parse_iso8601_duration(bad)


def test_videos_without_duration_are_excluded_not_fatal():
    """Live streams in progress carry no duration. One such item must not abort
    the run, and it must not be silently counted as a normal video."""

    def transport(endpoint, params):
        return {
            "etag": "vid-3",
            "items": [
                {
                    "id": "live",
                    "snippet": {"channelId": "UC_a", "title": "t",
                                "publishedAt": "2026-07-01T00:00:00Z"},
                    "statistics": {"viewCount": "10"},
                    "contentDetails": {},
                },
                {
                    "id": "normal",
                    "snippet": {"channelId": "UC_a", "title": "t",
                                "publishedAt": "2026-07-01T00:00:00Z"},
                    "statistics": {"viewCount": "10"},
                    "contentDetails": {"duration": "PT4M"},
                },
            ],
        }

    client = YouTubeClient(api_key="k", transport=transport)
    videos, _ledger = client.get_videos(["live", "normal"], QuotaLedger())
    assert [v.video_id for v in videos] == ["normal"]
