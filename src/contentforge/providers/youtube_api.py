"""YouTube Data API v3 client.

Network access is injected as a `transport` callable taking (endpoint, params)
and returning the parsed JSON body. Production passes a google-api-python-client
wrapper; tests pass a fixture reader, so CI never makes a network call and never
burns quota.

Every returned value is a Fact bound to the response etag, so downstream stages
can trace any number back to the exact API response it came from.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from contentforge.errors import MissingDataError
from contentforge.provenance import Fact, Provenance
from contentforge.providers.quota import QuotaLedger

API_ROOT = "https://www.googleapis.com/youtube/v3"

# channels.list and videos.list accept at most 50 ids per call; 51 returns
# HTTP 400 "invalidFilters". Verified against the live API.
MAX_IDS_PER_CALL = 50

# search.list caps at 50 results per call and costs 100 units either way,
# so asking for fewer wastes the call. Defaulting to 25 was why early runs
# sampled only a handful of channels per niche.
MAX_SEARCH_RESULTS = 50

Transport = Callable[[str, dict], dict]

# The time part is optional: live streams and upcoming premieres report "P0D",
# which is a real duration of zero rather than missing data.
_DURATION = re.compile(
    r"^P(?:(?P<days>\d+)D)?"
    r"(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


def parse_iso8601_duration(text: str) -> int:
    """YouTube returns durations as ISO 8601 (PT5M30S). Returns whole seconds."""
    match = _DURATION.match(text or "")
    if not match:
        raise MissingDataError(f"unparseable duration {text!r}")
    parts = {key: int(value or 0) for key, value in match.groupdict().items()}
    return (
        parts["days"] * 86400
        + parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
    )


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


@dataclass(frozen=True)
class VideoRecord:
    video_id: str
    channel_id: str
    title: str
    published_at: Fact
    view_count: Fact
    duration_seconds: Fact
    provenance: Provenance


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


def _batches(items: list, size: int = MAX_IDS_PER_CALL):
    for start in range(0, len(items), size):
        yield items[start : start + size]


class YouTubeClient:
    def __init__(self, api_key: str, transport: Transport) -> None:
        self._api_key = api_key
        self._transport = transport

    def search_channels(
        self, query: str, ledger: QuotaLedger, max_results: int = MAX_SEARCH_RESULTS
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

        current = ledger
        items: list[dict] = []
        prov = None
        for batch in _batches(channel_ids):
            params = {"id": ",".join(batch), "part": "snippet,statistics"}
            current = current.charge("channels.list")
            body = self._transport("channels.list", params)
            if prov is None:
                prov = _provenance("channels.list", params, body)
            items.extend(body.get("items") or [])

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
        return stats, current

    def channel_by_handle(
        self, handle: str, ledger: QuotaLedger
    ):
        """Resolve one channel by @handle. Costs 1 unit.

        channels.list with forHandle costs 1 unit against search.list's 100 and
        returns the exact channel rather than a best guess.
        """
        from contentforge.research.verify import ChannelFacts

        params = {"forHandle": handle, "part": "snippet,statistics"}
        charged = ledger.charge("channels.list")
        body = self._transport("channels.list", params)
        prov = _provenance("channels.list", params, body)

        items = body.get("items") or []
        if not items:
            raise MissingDataError(f"no channel found for handle @{handle}")

        item = items[0]
        snippet = _require(item, "snippet", "channel")
        statistics = _require(item, "statistics", "channel")
        published_raw = _require(snippet, "publishedAt", "channel snippet")
        return (
            ChannelFacts(
                channel_id=_require(item, "id", "channel"),
                title=_require(snippet, "title", "channel snippet"),
                subscribers=Fact(int(statistics.get("subscriberCount", 0)), prov),
                view_count=Fact(int(_require(statistics, "viewCount", "statistics")), prov),
                video_count=Fact(int(_require(statistics, "videoCount", "statistics")), prov),
                published_at=Fact(
                    datetime.fromisoformat(published_raw.replace("Z", "+00:00")), prov
                ),
            ),
            charged,
        )

    def get_uploads_playlists(
        self, channel_ids: list[str], ledger: QuotaLedger
    ) -> tuple[dict[str, str], QuotaLedger]:
        """Map each channel id to its uploads playlist id."""
        if not channel_ids:
            raise MissingDataError("get_uploads_playlists called with no ids")

        current = ledger
        mapping: dict[str, str] = {}
        for batch in _batches(channel_ids):
            params = {"id": ",".join(batch), "part": "contentDetails"}
            current = current.charge("channels.list")
            body = self._transport("channels.list", params)
            for item in body.get("items") or []:
                details = _require(item, "contentDetails", "channel")
                related = _require(details, "relatedPlaylists", "contentDetails")
                mapping[_require(item, "id", "channel")] = _require(
                    related, "uploads", "relatedPlaylists"
                )

        if not mapping:
            raise MissingDataError(f"no uploads playlists for {channel_ids!r}")
        return mapping, current

    def get_playlist_video_ids(
        self, playlist_id: str, ledger: QuotaLedger, max_videos: int = 50
    ) -> tuple[list[str], QuotaLedger]:
        params = {
            "playlistId": playlist_id,
            "part": "contentDetails",
            "maxResults": min(max_videos, MAX_IDS_PER_CALL),
        }
        charged = ledger.charge("playlistItems.list")
        body = self._transport("playlistItems.list", params)
        ids = [
            _require(
                _require(item, "contentDetails", "playlist item"),
                "videoId",
                "contentDetails",
            )
            for item in (body.get("items") or [])
        ]
        return ids, charged

    def get_videos(
        self, video_ids: list[str], ledger: QuotaLedger
    ) -> tuple[list[VideoRecord], QuotaLedger]:
        if not video_ids:
            raise MissingDataError("get_videos called with no ids")

        current = ledger
        records: list[VideoRecord] = []
        for batch in _batches(video_ids):
            params = {"id": ",".join(batch), "part": "snippet,statistics,contentDetails"}
            current = current.charge("videos.list")
            body = self._transport("videos.list", params)
            prov = _provenance("videos.list", params, body)
            for item in body.get("items") or []:
                snippet = _require(item, "snippet", "video")
                details = _require(item, "contentDetails", "video")
                # In-progress live streams and region-blocked items carry no
                # duration. Such a video cannot be characterised, so it is
                # excluded from the sample rather than guessed at. The drop is
                # visible to callers as a shortfall against len(video_ids).
                if "duration" not in details:
                    continue
                # viewCount is absent on brand-new videos. That is a genuine
                # zero, not missing data, so it must not raise.
                statistics = item.get("statistics") or {}
                published_raw = _require(snippet, "publishedAt", "video snippet")
                records.append(
                    VideoRecord(
                        video_id=_require(item, "id", "video"),
                        channel_id=_require(snippet, "channelId", "video snippet"),
                        title=_require(snippet, "title", "video snippet"),
                        published_at=Fact(
                            datetime.fromisoformat(published_raw.replace("Z", "+00:00")),
                            prov,
                        ),
                        view_count=Fact(int(statistics.get("viewCount", 0)), prov),
                        duration_seconds=Fact(
                            parse_iso8601_duration(
                                _require(details, "duration", "contentDetails")
                            ),
                            prov,
                        ),
                        provenance=prov,
                    )
                )
        return records, current


# Backwards-compatible alias: revision 1 named this MAX_IDS_PER_CHANNELS_CALL.
MAX_IDS_PER_CHANNELS_CALL = MAX_IDS_PER_CALL
