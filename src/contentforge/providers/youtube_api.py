"""YouTube Data API v3 client.

Network access is injected as a `transport` callable taking (endpoint, params)
and returning the parsed JSON body. Production passes a google-api-python-client
wrapper; tests pass a fixture reader, so CI never makes a network call and never
burns quota.

Every returned value is a Fact bound to the response etag, so downstream stages
can trace any number back to the exact API response it came from.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from contentforge.errors import MissingDataError
from contentforge.provenance import Fact, Provenance
from contentforge.providers.quota import QuotaLedger

API_ROOT = "https://www.googleapis.com/youtube/v3"

Transport = Callable[[str, dict], dict]


@dataclass(frozen=True)
class ChannelRef:
    channel_id: str
    title: str
    provenance: Provenance


@dataclass(frozen=True)
class ChannelStats:
    channel_id: str
    title: str
    subscribers: Fact
    video_count: Fact
    view_count: Fact
    published_at: Fact


def _provenance(endpoint: str, params: dict, body: dict) -> Provenance:
    """Build a Provenance from the response etag.

    A response without an etag cannot be cited, so it is rejected rather than
    given a synthesised id.
    """
    response_id = body.get("etag")
    if not response_id:
        raise MissingDataError(
            f"{endpoint} response carried no etag; cannot establish provenance"
        )
    query = "&".join(f"{key}={value}" for key, value in sorted(params.items()))
    resource = endpoint.split(".")[0]
    return Provenance(
        source_url=f"{API_ROOT}/{resource}?{query}",
        response_id=response_id,
        retrieved_at=datetime.now(timezone.utc),
    )


def _require(mapping: dict, key: str, context: str):
    if key not in mapping:
        raise MissingDataError(f"{context} missing required field {key!r}")
    return mapping[key]


class YouTubeClient:
    def __init__(self, api_key: str, transport: Transport) -> None:
        self._api_key = api_key
        self._transport = transport

    def search_channels(
        self, query: str, ledger: QuotaLedger, max_results: int = 25
    ) -> tuple[list[ChannelRef], QuotaLedger]:
        params = {
            "q": query,
            "type": "channel",
            "part": "snippet",
            "maxResults": max_results,
        }
        # Charge before calling: a request that reaches YouTube and then fails
        # has still consumed quota upstream.
        charged = ledger.charge("search.list")
        body = self._transport("search.list", params)
        prov = _provenance("search.list", params, body)

        items = body.get("items") or []
        if not items:
            raise MissingDataError(f"search returned no channels for {query!r}")

        refs = [
            ChannelRef(
                channel_id=_require(
                    _require(item, "id", "search item"), "channelId", "search id"
                ),
                title=_require(
                    _require(item, "snippet", "search item"), "title", "search snippet"
                ),
                provenance=prov,
            )
            for item in items
        ]
        return refs, charged

    def get_channels(
        self, channel_ids: list[str], ledger: QuotaLedger
    ) -> tuple[list[ChannelStats], QuotaLedger]:
        if not channel_ids:
            raise MissingDataError("get_channels called with no ids")

        params = {"id": ",".join(channel_ids), "part": "snippet,statistics"}
        charged = ledger.charge("channels.list")
        body = self._transport("channels.list", params)
        prov = _provenance("channels.list", params, body)

        items = body.get("items") or []
        if not items:
            raise MissingDataError(f"channels.list returned nothing for {channel_ids!r}")

        stats: list[ChannelStats] = []
        for item in items:
            channel_id = _require(item, "id", "channel item")
            statistics = _require(item, "statistics", f"channel {channel_id}")
            snippet = _require(item, "snippet", f"channel {channel_id}")
            published_raw = _require(snippet, "publishedAt", f"channel {channel_id} snippet")
            stats.append(
                ChannelStats(
                    channel_id=channel_id,
                    title=_require(snippet, "title", f"channel {channel_id} snippet"),
                    subscribers=Fact(
                        int(_require(statistics, "subscriberCount", "statistics")), prov
                    ),
                    video_count=Fact(
                        int(_require(statistics, "videoCount", "statistics")), prov
                    ),
                    view_count=Fact(
                        int(_require(statistics, "viewCount", "statistics")), prov
                    ),
                    published_at=Fact(
                        datetime.fromisoformat(published_raw.replace("Z", "+00:00")), prov
                    ),
                )
            )
        return stats, charged
