import json
from datetime import datetime, timezone
from pathlib import Path

from contentforge.cli import run_research
from contentforge.providers.quota import QuotaLedger
from contentforge.providers.youtube_api import YouTubeClient

NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)
TABLE = Path(__file__).parent.parent / "data" / "rpm_table.csv"

SEARCH = {
    "etag": "s1",
    "items": [
        {"id": {"channelId": "UC_a"}, "snippet": {"title": "A"}},
        {"id": {"channelId": "UC_b"}, "snippet": {"title": "B"}},
    ],
}
CHANNELS = {
    "etag": "c1",
    "items": [
        {
            "id": "UC_a",
            "snippet": {"title": "A", "publishedAt": "2025-01-01T00:00:00Z"},
            "statistics": {
                "subscriberCount": "50000",
                "videoCount": "80",
                "viewCount": "5000000",
            },
        },
        {
            "id": "UC_b",
            "snippet": {"title": "B", "publishedAt": "2026-01-01T00:00:00Z"},
            "statistics": {
                "subscriberCount": "3000",
                "videoCount": "20",
                "viewCount": "200000",
            },
        },
    ],
}


def transport(endpoint, params):
    return SEARCH if endpoint == "search.list" else CHANNELS


def test_run_research_produces_ranked_provenanced_report(tmp_path):
    client = YouTubeClient(api_key="k", transport=transport)
    scores, _ledger = run_research(
        client=client,
        niches={"finance": ["index funds"], "tech": ["ai tools"]},
        geography="US",
        table_path=TABLE,
        out_dir=tmp_path,
        now=NOW,
        ledger=QuotaLedger(),
    )
    assert len(scores) == 2
    assert scores[0].score >= scores[1].score, "results must be ranked"

    payload = json.loads((tmp_path / "report.json").read_text())
    for entry in payload["niches"]:
        assert entry["rpm_usd"]["source_url"].startswith("http")
        assert entry["metrics"]["competitor_count"]["source_url"].startswith("http")


def test_run_research_reports_actual_quota_spent(tmp_path):
    client = YouTubeClient(api_key="k", transport=transport)
    _scores, ledger = run_research(
        client=client,
        niches={"finance": ["index funds"]},
        geography="US",
        table_path=TABLE,
        out_dir=tmp_path,
        now=NOW,
        ledger=QuotaLedger(),
    )
    # 1 search.list (100) + 1 channels.list (1) = 101
    assert ledger.spent == 101


def test_full_default_config_stays_within_daily_quota(tmp_path):
    from contentforge.config import NICHE_QUERIES

    client = YouTubeClient(api_key="k", transport=transport)
    _scores, ledger = run_research(
        client=client,
        niches=NICHE_QUERIES,
        geography="US",
        table_path=TABLE,
        out_dir=tmp_path,
        now=NOW,
        ledger=QuotaLedger(),
    )
    # 3 niches x (3 searches x 100 + 1 channels.list) = 903
    assert ledger.spent == 903
    assert ledger.spent < 10_000, f"default config burns {ledger.spent} units/run"


def test_markdown_report_is_written_for_the_human_gate(tmp_path):
    client = YouTubeClient(api_key="k", transport=transport)
    run_research(
        client=client,
        niches={"finance": ["index funds"]},
        geography="US",
        table_path=TABLE,
        out_dir=tmp_path,
        now=NOW,
        ledger=QuotaLedger(),
    )
    assert (tmp_path / "report.md").exists()
