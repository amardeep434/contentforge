from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from contentforge.cli import run_research
from contentforge.errors import QuotaExceededError
from contentforge.providers.quota import QuotaLedger
from contentforge.providers.youtube_api import YouTubeClient

NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)
TABLE = Path(__file__).parent.parent / "data" / "niches.csv"
VIDEOS = 12


def make_transport(channels_per_search=4):
    """Fake YouTube where every channel breaks out halfway through its uploads."""

    def transport(endpoint, params):
        if endpoint == "search.list":
            return {
                "etag": "search-etag",
                "items": [
                    {"id": {"channelId": f"UC_{n}"}, "snippet": {"title": f"C{n}"}}
                    for n in range(channels_per_search)
                ],
            }
        if endpoint == "channels.list":
            ids = params["id"].split(",")
            return {
                "etag": "chan-etag",
                "items": [
                    {"id": cid, "contentDetails": {"relatedPlaylists": {"uploads": f"UU{cid}"}}}
                    for cid in ids
                ],
            }
        if endpoint == "playlistItems.list":
            playlist = params["playlistId"]
            return {
                "etag": "pl-etag",
                "items": [
                    {"contentDetails": {"videoId": f"{playlist}#v{n}"}}
                    for n in range(VIDEOS)
                ],
            }
        if endpoint == "videos.list":
            items = []
            for vid in params["id"].split(","):
                playlist, index_text = vid.split("#v")
                index = int(index_text)
                published = NOW - timedelta(days=400 - index * 20)
                views = 100 if index < VIDEOS // 2 else 500_000
                items.append(
                    {
                        "id": vid,
                        "snippet": {
                            "channelId": playlist[2:],
                            "title": "a reasonably long video title here",
                            "publishedAt": published.isoformat().replace("+00:00", "Z"),
                        },
                        "statistics": {"viewCount": str(views)},
                        "contentDetails": {"duration": "PT10M"},
                    }
                )
            return {"etag": "vid-etag", "items": items}
        raise AssertionError(f"unexpected endpoint {endpoint}")

    return transport


def run(tmp_path, limit=10_000_000):
    client = YouTubeClient(api_key="k", transport=make_transport())
    return run_research(
        client=client, niches=None, table_path=TABLE, out_dir=tmp_path,
        now=NOW, ledger=QuotaLedger(daily_limit=limit),
        channels_per_niche=4, videos_per_channel=VIDEOS,
    )


def test_ranks_every_niche_in_the_table(tmp_path):
    scores, _ledger = run(tmp_path)
    assert len(scores) >= 12, "v2 exists to cover breadth"
    assert scores[0].score >= scores[-1].score, "results must be ranked"


def test_detects_the_planted_breakout(tmp_path):
    scores, _ledger = run(tmp_path)
    assert scores[0].breakout_count > 0
    assert scores[0].median_lift > 1.0


def test_kids_carries_the_membership_penalty(tmp_path):
    scores, _ledger = run(tmp_path)
    kids = next(s for s in scores if s.niche == "kids")
    assert kids.membership_factor == 0.5


def test_high_rpm_niche_outranks_low_rpm_when_trajectories_match(tmp_path):
    """Every fake channel has an identical breakout, so RPM must break the tie."""
    scores, _ledger = run(tmp_path)
    finance = next(s for s in scores if s.niche == "finance" and s.geography == "US")
    gaming = next(s for s in scores if s.niche == "gaming")
    assert finance.score > gaming.score


def test_report_artifacts_are_written(tmp_path):
    run(tmp_path)
    assert (tmp_path / "report.json").exists()
    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "raw").is_dir()


def test_markdown_report_is_readable(tmp_path):
    run(tmp_path)
    longest = max(len(line) for line in (tmp_path / "report.md").read_text().split("\n"))
    assert longest < 300, f"longest line is {longest} chars"


def test_run_stops_cleanly_when_quota_exhausted(tmp_path):
    with pytest.raises(QuotaExceededError):
        run(tmp_path, limit=150)


def test_geography_filter_narrows_the_run(tmp_path):
    client = YouTubeClient(api_key="k", transport=make_transport())
    scores, _ledger = run_research(
        client=client, niches=None, table_path=TABLE, out_dir=tmp_path,
        now=NOW, ledger=QuotaLedger(daily_limit=10_000_000),
        channels_per_niche=4, videos_per_channel=VIDEOS, geography="IN",
    )
    assert {s.geography for s in scores} == {"IN"}
