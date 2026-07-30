"""Read Reddit through OpenCLI's browser bridge.

A better source than Threads for this work, for three reasons: `selftext` is the
whole post, so nothing hides behind a login wall or in reply images; `score` and
`comments` give a quality signal Threads does not expose; and subreddits like
r/aitubers are topic-scoped in a way a keyword search is not.

Requires the OpenCLI Chrome extension and a running daemon. Doctor reports these
platforms as `warn` even when the bridge is up, because it deliberately never
runs a platform command to verify a login - `warn` is not a fault here.

Posts are shaped to match `ThreadsPost` (author / permalink / posted_on / text /
images) so `gather_leads` consumes either without caring which it got. `score` is
an extra Reddit-only field; callers read it with getattr and a default.
"""

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from contentforge.errors import MissingDataError

OPENCLI = "opencli"


@dataclass(frozen=True)
class RedditPost:
    author: str
    permalink: str
    posted_on: str
    text: str
    images: tuple[str, ...]
    source_url: str
    retrieved_at: datetime
    subreddit: str = ""
    score: int = 0
    comments: int = 0
    title: str = field(default="")


def run_opencli(args: list[str]) -> str:
    """Invoke OpenCLI, surfacing its stderr rather than an empty result.

    A bridge that is down fails here, and it must not look like "no posts
    matched" - that would silently understate every count downstream.
    """
    try:
        finished = subprocess.run(
            [OPENCLI, *args], capture_output=True, text=True, timeout=180
        )
    except FileNotFoundError:
        raise MissingDataError(
            "opencli is not installed; Reddit needs the OpenCLI browser bridge"
        ) from None
    except subprocess.TimeoutExpired:
        raise MissingDataError("opencli timed out; is Chrome open?") from None
    if finished.returncode != 0:
        detail = (finished.stderr or finished.stdout or "").strip()[:200]
        raise MissingDataError(f"opencli failed: {detail}")
    return finished.stdout


def parse_posts(payload: str, source_url: str, now: datetime) -> list[RedditPost]:
    try:
        records = json.loads(payload)
    except json.JSONDecodeError:
        raise MissingDataError(
            f"opencli returned no parseable JSON for {source_url}"
        ) from None
    if isinstance(records, dict):
        records = records.get("results") or records.get("data") or []
    if not records:
        raise MissingDataError(
            f"no Reddit posts for {source_url}. Either nothing matched, or the "
            "browser session is not logged in - both need a human look rather "
            "than an empty result."
        )

    posts: list[RedditPost] = []
    for record in records:
        created = record.get("created_utc")
        try:
            posted_on = (
                datetime.fromtimestamp(int(created), tz=timezone.utc).date().isoformat()
                if created
                else ""
            )
        except (TypeError, ValueError):
            posted_on = ""
        images = [
            url
            for url in [record.get("preview_image_url", "")]
            + list(record.get("gallery_urls") or [])
            if url
        ]
        title = record.get("title", "")
        body = record.get("selftext", "")
        posts.append(
            RedditPost(
                author=record.get("author", ""),
                permalink=record.get("url", ""),
                posted_on=posted_on,
                # Title first: it carries the claim, and a truncated read still
                # sees what the post is about.
                text=f"{title}\n\n{body}".strip(),
                images=tuple(images),
                source_url=source_url,
                retrieved_at=now,
                subreddit=record.get("subreddit", ""),
                score=int(record.get("score") or 0),
                comments=int(record.get("comments") or 0),
                title=title,
            )
        )
    return posts


def search_reddit(
    query: str,
    runner: Callable[[list[str]], str] = run_opencli,
    now: datetime | None = None,
    subreddit: str = "",
    sort: str = "relevance",
    time_filter: str = "all",
    limit: int = 15,
    serp_type: str = "",
) -> list[RedditPost]:
    """Search Reddit. `serp_type` is accepted and ignored, to match the
    Threads searcher's signature so `gather_leads` can take either."""
    args = ["reddit", "search", query, "-f", "json", "--limit", str(limit),
            "--sort", sort, "--time", time_filter]
    if subreddit:
        args += ["--subreddit", subreddit]
    label = f"reddit:{subreddit or 'all'}:{query}"
    return parse_posts(runner(args), label, now or datetime.now(timezone.utc))
