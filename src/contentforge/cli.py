"""Command line entry point.

    pipeline research [--geography US] [--out data/research]

Reads YOUTUBE_API_KEY from the environment and fails loudly if it is absent.
Credentials are never read from anywhere but the environment, and never logged.
"""

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

from contentforge.config import DEFAULT_GEOGRAPHY, NICHE_QUERIES
from contentforge.providers.quota import QuotaLedger
from contentforge.providers.youtube_api import YouTubeClient
from contentforge.research.discover import discover_niche
from contentforge.research.metrics import compute_metrics
from contentforge.research.report import write_report
from contentforge.research.rpm_table import load_rpm_table, rpm_midpoint_usd
from contentforge.research.score import NicheScore, rank, score_niche


def run_research(
    client: YouTubeClient,
    niches: dict[str, list[str]],
    geography: str,
    table_path: Path,
    out_dir: Path,
    now: datetime,
    ledger: QuotaLedger,
) -> tuple[list[NicheScore], QuotaLedger]:
    """Score every niche and write the report.

    Returns the ranked scores and the final ledger, so callers can assert on
    quota actually consumed rather than trusting it.
    """
    table = load_rpm_table(table_path)
    current = ledger
    scores: list[NicheScore] = []

    for niche, queries in niches.items():
        candidate, current = discover_niche(client, niche, queries, current)
        channel_stats, current = client.get_channels(list(candidate.channel_ids), current)
        metrics = compute_metrics(candidate, channel_stats, now)
        rpm = rpm_midpoint_usd(table, niche, geography)
        scores.append(score_niche(metrics, rpm, geography))

    ranked = rank(scores)
    write_report(ranked, out_dir, now)
    return ranked, current


def _live_transport(api_key: str):
    from googleapiclient.discovery import build

    service = build("youtube", "v3", developerKey=api_key, cache_discovery=False)

    def _transport(endpoint: str, params: dict) -> dict:
        resource, method = endpoint.split(".")
        return getattr(getattr(service, resource)(), method)(**params).execute()

    return _transport


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    research = subparsers.add_parser(
        "research", help="rank niches from live YouTube data"
    )
    research.add_argument("--geography", default=DEFAULT_GEOGRAPHY)
    research.add_argument("--out", type=Path, default=Path("data/research"))
    args = parser.parse_args(argv)

    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        raise SystemExit("YOUTUBE_API_KEY is not set (copy .env.example to .env)")

    now = datetime.now(timezone.utc)
    out_dir = args.out / now.date().isoformat()
    client = YouTubeClient(api_key=api_key, transport=_live_transport(api_key))

    ranked, ledger = run_research(
        client=client,
        niches=NICHE_QUERIES,
        geography=args.geography,
        table_path=Path("data/rpm_table.csv"),
        out_dir=out_dir,
        now=now,
        ledger=QuotaLedger(),
    )
    print(
        f"Wrote {len(ranked)} ranked niches to {out_dir} "
        f"({ledger.spent} of {ledger.daily_limit} quota units used)"
    )
    return 0
