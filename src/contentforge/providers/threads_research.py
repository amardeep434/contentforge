"""Read Threads without an API key, a login, or a browser extension.

The design doc listed this module as unimplementable until Apify, on the
assumption that Threads reading required either the official API (App Review,
2-4 weeks) or authenticated scraping. Neither is true for reading: Jina Reader
renders both public profiles and keyword search to markdown, unauthenticated.

Publishing still requires the official Threads API. Reading was never the
blocker.

**What this returns is claims, not evidence** - but many of them are checkable.
The channel under discussion is usually named in an attached screenshot rather
than the caption, so `images` is part of the record and reading it is how a
claim becomes a lead. Two claims found this way verified exactly against the
Data API at 1 unit each; a first pass that ignored the images concluded, wrongly,
that none of them could be checked.

Treat every number here as an assertion by a stranger until `pipeline verify`
says otherwise.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import quote

from contentforge.errors import MissingDataError

READER = "https://r.jina.ai/"
BASE = "https://www.threads.net"

# A post in Jina's rendering is: a bare [handle](profile-url) line, then a
# [date](permalink) line, then body text, then engagement counts on their own
# lines. The permalink line is the only reliable anchor - handles also appear in
# image alt text and navigation - so parsing keys off it.
_PERMALINK = re.compile(
    r"\[([^\]]+)\]\((https://www\.threads\.(?:net|com)/@([\w.]+)/post/[\w-]+)\)"
)
_COUNT_ONLY = re.compile(r"^[\d,.]+[KM]?$")
# Posts carry screenshots - YouTube Studio panels, channel pages - and the
# channel being discussed is usually named only there, never in the caption.
# Dropping these makes a checkable claim look uncheckable.
# Alt text is captured so avatars can be dropped: Jina renders them as
# "Image 5: someone's profile picture", and a run that keeps them fills the
# review step with thumbnails of people's faces instead of evidence.
_IMAGE = re.compile(r"!\[Image[^\]:]*(:[^\]]*)?\]\((https://scontent[^)]+)\)")
# Whole links, plus the orphan "](url)" tail Jina leaves when it splits a
# markdown link across two lines.
_MARKDOWN_NOISE = re.compile(r"!?\[[^\]]*\]\([^)]*\)|\]\([^)]*\)")

# Threads renders roughly four posts, then a login prompt. Everything from here
# on is page chrome; appending it to the last post silently corrupts the record.
_LOGIN_WALL = ("Log in to see more", "Log in or sign up", "See what people are talking")


@dataclass(frozen=True)
class ThreadsPost:
    """One post, carrying where and when it was retrieved.

    `source_url` is the query that produced it, not the post's own permalink -
    a claim's discovery path matters as much as its content when the content is
    unverifiable.
    """

    author: str
    permalink: str
    posted_on: str
    text: str
    images: tuple[str, ...]
    source_url: str
    retrieved_at: datetime


def profile_url(handle: str) -> str:
    return f"{BASE}/@{handle.lstrip('@')}"


def search_url(query: str, serp_type: str = "default") -> str:
    return f"{BASE}/search?q={quote(query)}&serp_type={serp_type}"


def http_get(url: str, render_seconds: int = 0) -> str:
    """Fetch through Jina Reader.

    `render_seconds` asks Jina to wait for client-side rendering. Threads loads
    a post's replies with JavaScript, so without it a permalink returns only the
    top-level post - which is usually a teaser ending in "here's how I did it:"
    with every actual step in the replies below.
    """
    import urllib.request

    headers = {"User-Agent": "contentforge/0.1"}
    if render_seconds:
        headers["x-timeout"] = str(render_seconds)
    request = urllib.request.Request(READER + url, headers=headers)
    with urllib.request.urlopen(request, timeout=45 + render_seconds * 2) as response:
        return response.read().decode("utf-8", errors="replace")


def http_get_rendered(url: str) -> str:
    return http_get(url, render_seconds=20)


def read_thread(
    permalink: str,
    transport: Callable[[str], str] = http_get_rendered,
    now: datetime | None = None,
) -> list[ThreadsPost]:
    """Every post in a thread: the root, then the replies beneath it.

    The author's own replies are the step-by-step payload and are usually
    screenshots, so their `images` matter more than their (often empty) text.
    Filter on `author` to separate the author's continuation from commenters.
    """
    return _fetch(permalink, transport, now)


def _clean(line: str) -> str:
    return _MARKDOWN_NOISE.sub("", line).strip()


def parse_posts(markdown: str, source_url: str, now: datetime) -> list[ThreadsPost]:
    """Extract posts from Jina's markdown rendering.

    Raises rather than returning an empty list: a broken parser and an account
    with no posts produce identical output otherwise, and the pipeline would
    record "no data" as though it were a finding.
    """
    lines = markdown.splitlines()
    anchors = [
        (index, match)
        for index, line in enumerate(lines)
        if (match := _PERMALINK.search(line))
    ]
    if not anchors:
        raise MissingDataError(
            f"no posts parsed from {source_url}. Either the account is empty, the "
            "page required a login, or Jina's rendering changed - all three need "
            "a human look rather than an empty result."
        )

    posts: list[ThreadsPost] = []
    for position, (index, match) in enumerate(anchors):
        stop = anchors[position + 1][0] if position + 1 < len(anchors) else len(lines)
        body: list[str] = []
        images: list[str] = []
        for raw in lines[index + 1 : stop]:
            images.extend(
                url
                for alt, url in _IMAGE.findall(raw)
                if "profile picture" not in alt.lower()
            )
            text = _clean(raw)
            if text.startswith(_LOGIN_WALL):
                break
            # Engagement counts sit alone on their own lines under each post.
            if not text or _COUNT_ONLY.match(text):
                continue
            body.append(text)
        posts.append(
            ThreadsPost(
                author=match.group(3),
                permalink=match.group(2),
                posted_on=match.group(1),
                text=" ".join(body).strip(),
                images=tuple(dict.fromkeys(images)),
                source_url=source_url,
                retrieved_at=now,
            )
        )
    return posts


def _fetch(url: str, transport: Callable[[str], str], now: datetime | None):
    now = now or datetime.now(timezone.utc)
    try:
        markdown = transport(url)
    except MissingDataError:
        raise
    except Exception as error:
        # Network and reader failures are indistinguishable to the caller and
        # both mean the same thing: nothing was collected.
        raise MissingDataError(f"could not read {url}: {type(error).__name__}") from None
    return parse_posts(markdown, url, now)


def read_profile(
    handle: str, transport: Callable[[str], str] = http_get, now: datetime | None = None
) -> list[ThreadsPost]:
    return _fetch(profile_url(handle), transport, now)


def search_threads(
    query: str,
    transport: Callable[[str], str] = http_get,
    now: datetime | None = None,
    serp_type: str = "default",
) -> list[ThreadsPost]:
    return _fetch(search_url(query, serp_type), transport, now)
