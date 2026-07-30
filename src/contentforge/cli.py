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
from contentforge.providers.quota_monitor import (
    DEFAULT_QUOTA_ID,
    SEARCH_QUOTA_ID,
    from_local_ledger,
    read_authoritative_usage,
)
from contentforge.providers.quota_store import (
    estimate_run_cost,
    load_ledger,
    quota_date,
    require_headroom,
    save_ledger,
)
from contentforge.providers.youtube_api import YouTubeClient
from contentforge.research.changes import describe_change
from contentforge.research.niches import load_niches, rpm_midpoint_usd
from contentforge.research.report import write_report
from contentforge.research.score import NicheScore, rank, score_niche
from contentforge.research.trajectory import MIN_SIDE_VIDEOS, build_trajectory
from contentforge.research.verify import check_claim, format_check

MIN_VIDEOS_FOR_TRAJECTORY = MIN_SIDE_VIDEOS * 2
QUOTA_DIR = Path("data/quota")


def _credential(profile: str | None) -> tuple[str, Path]:
    """Resolve the API key and its ledger file for a named profile.

    Profiles exist for key rotation and for genuinely separate registered API
    Clients. They are NOT a quota pool: the YouTube API Developer Policies
    require exactly one API Project per API Client, so each profile carries its
    own independent ledger and the pipeline never fails over between them.
    """
    variable = "YOUTUBE_API_KEY" if not profile else f"YOUTUBE_API_KEY_{profile.upper()}"
    key = os.environ.get(variable)
    if not key:
        raise SystemExit(f"{variable} is not set (copy .env.example to .env)")
    name = profile.lower() if profile else "default"
    return key, QUOTA_DIR / f"{name}.json"
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
    parser.add_argument(
        "--profile", default=None,
        help="named credential (reads YOUTUBE_API_KEY_<PROFILE>); each profile "
             "has its own independent quota ledger and is never failed over to",
    )
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

    subparsers.add_parser("quota", help="show quota usage, local and authoritative")

    threads = subparsers.add_parser(
        "threads",
        help="read Threads posts (no API key, no quota) - claims, not evidence",
    )
    threads.add_argument("query", help="search term, or @handle to read a profile")
    threads.add_argument(
        "--tags", action="store_true", help="search the tag feed instead of posts"
    )
    threads.add_argument(
        "--limit", type=int, default=20, help="maximum posts to print"
    )

    verify = subparsers.add_parser(
        "verify", help="check a claimed channel statistic against the API"
    )
    verify.add_argument("handles", nargs="+", help="channel @handles")
    verify.add_argument(
        "--claimed-views", type=int, default=None,
        help="view count asserted by the source, to compare against",
    )
    verify.add_argument(
        "--rpm", type=float, default=None,
        help="assumed RPM for an implied earnings figure (never a measurement)",
    )
    args = parser.parse_args(argv)

    if args.command == "threads":
        from contentforge.providers.threads_research import (
            read_profile,
            search_threads,
        )

        if args.query.startswith("@"):
            posts = read_profile(args.query)
        else:
            posts = search_threads(
                args.query, serp_type="tags" if args.tags else "default"
            )
        for post in posts[: args.limit]:
            print(f"@{post.author} [{post.posted_on}] {post.text}")
            print(f"    {post.permalink}")
        print(
            f"\n{len(posts)} posts. These are unverified claims by strangers. "
            f"Any channel named here costs 1 quota unit to check with "
            f"`pipeline verify`; a claim naming no channel cannot be checked "
            f"at all."
        )
        return 0


    api_key, ledger_path = _credential(args.profile)

    client_for = lambda: YouTubeClient(api_key=api_key, transport=_live_transport(api_key))

    if args.command == "quota":
        now = datetime.now(timezone.utc)
        ledger = load_ledger(ledger_path, now)
        local = from_local_ledger(ledger.spent, ledger.daily_limit)
        print(f"Quota for {quota_date(now)} (profile: {args.profile or 'default'})\n")
        print(f"  local forecast   {local.spent:,} of {local.limit:,} "
              f"({local.remaining:,} remaining)")
        print(f"                   {local.detail}\n")
        for quota_id in (DEFAULT_QUOTA_ID, SEARCH_QUOTA_ID):
            reading = read_authoritative_usage(now, quota_id)
            value = f"{reading.spent:,}" if reading.is_known else "UNKNOWN"
            print(f"  {quota_id:<24} {value}")
            print(f"                   {reading.detail}")
        return 0

    if args.command == "verify":
        client = client_for()
        now = datetime.now(timezone.utc)
        ledger = load_ledger(ledger_path, now)
        started_at = ledger.spent
        try:
            for handle in args.handles:
                check, ledger = check_claim(
                    client, handle, ledger,
                    claimed_views=args.claimed_views, assumed_rpm=args.rpm,
                )
                print(format_check(check))
                print()
        finally:
            # Persist on failure too: units charged before a transport error
            # may already be gone from the real counter.
            save_ledger(ledger_path, ledger, now, started_at)
        print(f"({ledger.spent:,} of {ledger.daily_limit:,} quota units used today)")
        return 0

    now = datetime.now(timezone.utc)
    out_dir = args.out / now.date().isoformat()
    client = YouTubeClient(api_key=api_key, transport=_live_transport(api_key))

    ledger = load_ledger(ledger_path, now)
    started_at = ledger.spent
    niche_count = len(load_niches(Path("data/niches.csv")))
    estimated = estimate_run_cost(
        niches=niche_count, queries_per_niche=2,
        channels_per_niche=args.channels_per_niche,
    )
    authoritative = read_authoritative_usage(now)
    if authoritative.is_known:
        print(
            f"Quota for {quota_date(now)}: {authoritative.spent:,} spent "
            f"(Cloud Monitoring). This run needs ~{estimated:,}."
        )
        if authoritative.spent + estimated > ledger.daily_limit:
            raise SystemExit(
                f"run needs ~{estimated:,} units but Cloud Monitoring reports "
                f"{authoritative.spent:,} of {ledger.daily_limit:,} already spent today"
            )
    else:
        print(
            f"Quota for {quota_date(now)}: {ledger.spent:,} spent per the LOCAL "
            f"forecast. This run needs ~{estimated:,}.\n"
            f"  WARNING: authoritative usage unavailable - {authoritative.detail}\n"
            f"  The local figure counts only calls this pipeline recorded, so the "
            f"real remaining quota may be far lower."
        )
    require_headroom(ledger, estimated)

    try:
            ranked, ledger = run_research(
            client=client,
            niches=None,
            table_path=Path("data/niches.csv"),
            out_dir=out_dir,
            now=now,
            ledger=ledger,
            channels_per_niche=args.channels_per_niche,
            videos_per_channel=args.videos_per_channel,
            geography=args.geography,
        )
    finally:
        # Persist whatever was spent, including on a failed run - those units
        # are gone from the real counter either way.
        save_ledger(ledger_path, ledger, now, started_at)

    print(
        f"Wrote {len(ranked)} ranked niches to {out_dir} "
        f"({ledger.spent:,} of {ledger.daily_limit:,} quota units used today)"
    )
    return 0
