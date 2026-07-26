"""Command line entry point.

    pipeline research [--geography US] [--out data/research]
                      [--channels-per-niche 100] [--videos-per-channel 50]

Reads YOUTUBE_API_KEY from the environment and fails loudly if absent.
Credentials come only from the environment and are never logged.
"""

import argparse
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from contentforge.errors import (
    ContentforgeError,
    MissingDataError,
    ResourceNotFoundError,
)
from contentforge.providers.quota import QuotaLedger
from contentforge.providers.youtube_api import YouTubeClient
from contentforge.research.changes import describe_change
from contentforge.research.niches import load_niches, rpm_midpoint_usd
from contentforge.research.report import write_report
from contentforge.research.score import NicheScore, rank, score_niche
from contentforge.research.trajectory import MIN_SIDE_VIDEOS, build_trajectory

MIN_VIDEOS_FOR_TRAJECTORY = MIN_SIDE_VIDEOS * 2
DEFAULT_CHANNELS_PER_NICHE = 100
DEFAULT_VIDEOS_PER_CHANNEL = 50


def _collect_channel_ids(client, niche, ledger, limit):
    """Search every seed query, dedupe, and stop at the limit."""
    channel_ids: list[str] = []
    current = ledger
    for query in niche.seed_queries:
        if len(channel_ids) >= limit:
            break
        refs, current = client.search_channels(query, current)
        for ref in refs:
            if ref.channel_id not in channel_ids:
                channel_ids.append(ref.channel_id)
    return channel_ids[:limit], current


def _trajectories_for(client, playlists, ledger, now, videos_per_channel):
    """Build a trajectory per channel, skipping those too young to read.

    A channel with fewer than MIN_VIDEOS_FOR_TRAJECTORY uploads is skipped
    rather than failed — having no trajectory is the honest answer for it, not
    an error in the run.
    """
    current = ledger
    trajectories = []
    profiles = []
    for channel_id, playlist_id in playlists.items():
        try:
            video_ids, current = client.get_playlist_video_ids(
                playlist_id, current, max_videos=videos_per_channel
            )
        except ResourceNotFoundError:
            # Terminated or fully private channels keep an uploads playlist id
            # that no longer resolves. Skip the channel; the run continues.
            continue
        if len(video_ids) < MIN_VIDEOS_FOR_TRAJECTORY:
            continue
        videos, current = client.get_videos(video_ids, current)
        if len(videos) < MIN_VIDEOS_FOR_TRAJECTORY:
            continue
        trajectory = build_trajectory(channel_id, videos, now)
        trajectories.append(trajectory)
        profile = describe_change(trajectory)
        if profile is not None:
            profiles.append(profile)
    return trajectories, profiles, current


def run_research(
    client: YouTubeClient,
    niches,
    table_path: Path,
    out_dir: Path,
    now: datetime,
    ledger: QuotaLedger,
    channels_per_niche: int = DEFAULT_CHANNELS_PER_NICHE,
    videos_per_channel: int = DEFAULT_VIDEOS_PER_CHANNEL,
    geography: str | None = None,
) -> tuple[list[NicheScore], QuotaLedger]:
    """Score every niche in the table and write the report.

    Returns the ranked scores and the final ledger, so callers can assert on
    quota actually consumed rather than trusting it.
    """
    table = niches if niches is not None else load_niches(table_path)
    current = ledger
    scores: list[NicheScore] = []
    change_profiles: dict[str, list] = {}
    raw_responses: dict[str, dict] = {}

    for (name, geo), niche in table.items():
        if geography is not None and geo != geography:
            continue

        channel_ids, current = _collect_channel_ids(
            client, niche, current, channels_per_niche
        )
        if not channel_ids:
            continue

        playlists, current = client.get_uploads_playlists(channel_ids, current)
        trajectories, profiles, current = _trajectories_for(
            client, playlists, current, now, videos_per_channel
        )
        if not trajectories:
            continue

        scores.append(score_niche(niche, trajectories, rpm_midpoint_usd(niche)))
        change_profiles[name] = profiles

    if not scores:
        raise MissingDataError("no niche produced a scorable sample")

    ranked = rank(scores)
    write_report(ranked, change_profiles, raw_responses, out_dir, now)
    return ranked, current


def _redact(text: str) -> str:
    """Strip API keys from error text.

    googleapiclient embeds the full request URL - including key=... - in its
    exception messages, so an unhandled traceback would print the credential.
    """
    return re.sub(r"key=[A-Za-z0-9_\-]+", "key=REDACTED", text)


def _live_transport(api_key: str):
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    service = build("youtube", "v3", developerKey=api_key, cache_discovery=False)

    def _transport(endpoint: str, params: dict) -> dict:
        resource, method = endpoint.split(".")
        try:
            return getattr(getattr(service, resource)(), method)(**params).execute()
        except HttpError as error:
            message = _redact(str(error))
            if error.resp.status == 404:
                raise ResourceNotFoundError(message) from None
            raise ContentforgeError(message) from None

    return _transport


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    research = subparsers.add_parser(
        "research", help="rank niches from live YouTube data"
    )
    research.add_argument("--geography", default=None)
    research.add_argument("--out", type=Path, default=Path("data/research"))
    research.add_argument(
        "--channels-per-niche", type=int, default=DEFAULT_CHANNELS_PER_NICHE
    )
    research.add_argument(
        "--videos-per-channel", type=int, default=DEFAULT_VIDEOS_PER_CHANNEL
    )
    args = parser.parse_args(argv)

    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        raise SystemExit("YOUTUBE_API_KEY is not set (copy .env.example to .env)")

    now = datetime.now(timezone.utc)
    out_dir = args.out / now.date().isoformat()
    client = YouTubeClient(api_key=api_key, transport=_live_transport(api_key))

    ranked, ledger = run_research(
        client=client,
        niches=None,
        table_path=Path("data/niches.csv"),
        out_dir=out_dir,
        now=now,
        ledger=QuotaLedger(),
        channels_per_niche=args.channels_per_niche,
        videos_per_channel=args.videos_per_channel,
        geography=args.geography,
    )
    print(
        f"Wrote {len(ranked)} ranked niches to {out_dir} "
        f"({ledger.spent} of {ledger.daily_limit} quota units used)"
    )
    return 0
