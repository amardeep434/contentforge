"""Is this channel actually a faceless operation, or a person?

Added after Art History Explained — the exemplar this project selected a niche
around — turned out to be Christopher P Jones, an art-history writer narrating
his own work with a 6,000-subscriber Substack behind him (C-048). It was watched
four times, transcribed, and profiled across three scans without anyone noticing
the tip-jar link in its description.

A channel's metrics say nothing about who is behind it. A person with domain
expertise and an existing audience can produce numbers a pipeline cannot
reproduce, and "faceless" had been inferred from the format rather than checked.

The check is free: video descriptions come from yt-dlp with no API quota.

**This classifier is deliberately one-directional.** Finding a tip jar proves a
person; finding nothing proves only that nothing was found. `UNKNOWN` is
therefore the default, and it is not the same as `FACELESS`.
"""

import re
import subprocess
from dataclasses import dataclass

#: A person monetising themselves directly. The strongest available signal:
#: faceless channels take ad revenue, not tips.
_TIP_JARS = (
    "ko-fi.com",
    "patreon.com",
    "buymeacoffee.com",
    "paypal.me",
    "gofundme.com",
)

#: A personal publication implies an author with a name and a following.
_PERSONAL_PLATFORMS = ("substack.com", "beehiiv.com", "ghost.io", "medium.com/@")

#: First-person authorship claims. "my newsletter" is a person; "our channel"
#: is not necessarily.
_FIRST_PERSON = (
    r"\bleave me a tip\b",
    r"\bmy newsletter\b",
    r"\bmy substack\b",
    r"\bmy book\b",
    r"\bmy course\b",
    r"\bmy website\b",
    r"\bi'?m an? (writer|artist|historian|teacher|author|journalist)\b",
    r"\bmy name is\b",
    r"\bfollow me on\b",
    r"\bwritten and narrated by\b",
    r"\bnarrated by\b",
)

FACELESS = "faceless"
PERSONAL = "personal"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class OperatorVerdict:
    kind: str
    evidence: str

    @property
    def is_personal(self) -> bool:
        return self.kind == PERSONAL


def classify_operator(text: str) -> OperatorVerdict:
    """Classify from channel and video description text.

    Returns UNKNOWN rather than FACELESS when nothing is found — absence of a
    tip jar is not evidence of absence of a person.
    """
    if not (text or "").strip():
        return OperatorVerdict(UNKNOWN, "no description text available")

    lowered = text.lower()
    found: list[str] = []
    for domain in _TIP_JARS:
        if domain in lowered:
            found.append(f"tip jar: {domain}")
    for domain in _PERSONAL_PLATFORMS:
        if domain in lowered:
            found.append(f"personal publication: {domain}")
    for pattern in _FIRST_PERSON:
        match = re.search(pattern, lowered)
        if match:
            found.append(f"first person: {match.group(0)!r}")

    if found:
        return OperatorVerdict(PERSONAL, "; ".join(found[:4]))
    return OperatorVerdict(
        UNKNOWN,
        "no personal-brand signals found — this is not proof of a faceless "
        "operation, only that none were detected",
    )


def channel_url(channel_id: str) -> str:
    """Build a fetchable URL from a channel **id**, never a handle.

    A guessed handle 404s, and this check would then silently report UNKNOWN -
    the safe default, but useless. Handle-guessing is 5-for-5 wrong in this
    project (C-008); the id always resolves. The `/videos` tab is required, as
    the bare channel URL does not enumerate uploads.
    """
    if not channel_id.startswith("UC"):
        raise ValueError(
            f"{channel_id!r} is not a channel id; pass the id from the API, "
            "never a handle guessed from a display name"
        )
    return f"https://www.youtube.com/channel/{channel_id}/videos"


def fetch_descriptions(channel_url: str, videos: int = 3) -> str:
    """Video descriptions for a channel. Free — yt-dlp, no API quota."""
    try:
        finished = subprocess.run(
            [
                "yt-dlp",
                "--skip-download",
                "--playlist-end",
                str(videos),
                "--print",
                "%(description)s",
                channel_url,
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return finished.stdout or ""


def check_channel(
    channel_url: str, fetcher=fetch_descriptions, videos: int = 3
) -> OperatorVerdict:
    return classify_operator(fetcher(channel_url, videos))
