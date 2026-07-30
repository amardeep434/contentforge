"""Turn social-media claims into checked facts.

The loop this implements, learned the expensive way:

    1. search Threads (free, no quota)          gather_leads
    2. download the attached screenshots        gather_leads
    3. read the screenshots for channel names   <- needs eyes, see SKILL
    4. resolve each handle, profile it          profile_handles
    5. record claim beside measurement          write_report

Step 3 is why this is two stages rather than one function. The channel under
discussion is usually named only inside a Studio screenshot, never in the
caption - a first pass that read captions alone concluded, wrongly, that none of
these claims could be checked (C-039). Automating steps 1-2 and 4-5 and leaving
a human or a vision model in the middle is the honest shape.

Handles found in caption text are extracted automatically, since that costs
nothing. They are usually the poster's own channel rather than the one being
discussed, so they supplement the screenshots and do not replace them.
"""

import json
import re
import statistics as st
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from contentforge.errors import MissingDataError

# youtube.com/@handle, youtu.be/@handle, or a bare @handle in the caption.
_YT_URL = re.compile(
    r"youtube\.com/(?:@|c/|channel/|user/)([A-Za-z0-9_.\-]{3,30})", re.I
)
_BARE = re.compile(r"(?<![\w/])@([A-Za-z0-9_.\-]{3,30})")

# Captions that quote money without naming a channel are the common case; these
# let the report say how many leads were dead on arrival rather than hiding it.
_MONEY = re.compile(r"\$[\d,]+(?:\.\d+)?|\d+(?:\.\d+)?[KM]\s*(?:subs|views)", re.I)


@dataclass(frozen=True)
class Lead:
    """A claim, where it came from, and what it might be checkable against."""

    author: str
    permalink: str
    posted_on: str
    claim: str
    money_mentioned: tuple[str, ...]
    handles_from_text: tuple[str, ...]
    image_paths: tuple[str, ...]
    # Screenshots from the author's own replies. On Threads the top-level post
    # is usually a teaser ("here's how I did it:") and every actual step is a
    # reply, posted as an image. Without these the lead is just the headline.
    reply_image_paths: tuple[str, ...] = field(default=())
    # Filled in after someone reads the screenshots. Empty means "not yet read",
    # which is deliberately distinct from "read, found nothing".
    handles_from_images: tuple[str, ...] = field(default=())

    @property
    def all_handles(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(self.handles_from_text + self.handles_from_images))


def extract_handles(text: str, exclude: str = "") -> tuple[str, ...]:
    """Channel handles mentioned in caption text, minus the poster's own."""
    found = _YT_URL.findall(text) + _BARE.findall(text)
    skip = {exclude.lower().lstrip("@")}
    return tuple(
        dict.fromkeys(h for h in found if h.lower() not in skip and len(h) >= 3)
    )


def money_in(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_MONEY.findall(text)))


def download_image(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "contentforge/0.1"})
    with urllib.request.urlopen(request, timeout=45) as response:
        destination.write_bytes(response.read())
    return destination


def gather_leads(
    query: str,
    out_dir: Path,
    search: Callable,
    fetch_image: Callable[[str, Path], Path] = download_image,
    serp_type: str = "default",
    max_images: int = 2,
    expand: Callable | None = None,
    max_expand: int = 8,
    max_reply_images: int = 8,
) -> list[Lead]:
    """Stage 1: collect posts and pull down their screenshots.

    A post whose images all fail to download is still recorded - the claim and
    its permalink remain useful, and silently dropping it would understate how
    much of the source could not be read.
    """
    posts = search(query, serp_type=serp_type)
    leads: list[Lead] = []
    # Expanding costs a slow rendered fetch each, so it is bounded and spent on
    # the posts most likely to carry a worked example.
    worth_expanding = {
        p.permalink
        for p in sorted(posts, key=lambda p: -len(money_in(p.text)))[:max_expand]
    }
    for index, post in enumerate(posts, start=1):
        paths: list[str] = []
        for position, url in enumerate(post.images[:max_images], start=1):
            target = out_dir / "images" / f"{index:02d}_{post.author}_{position}.jpg"
            try:
                paths.append(str(fetch_image(url, target)))
            except Exception:
                continue
        reply_paths: list[str] = []
        if expand is not None and post.permalink in worth_expanding:
            try:
                thread = expand(post.permalink)
            except Exception:
                thread = []
            # Only the author's own replies are the walkthrough; other people's
            # images are unrelated.
            urls = [
                url
                for reply in thread[1:]
                if reply.author == post.author
                for url in reply.images
            ]
            for position, url in enumerate(urls[:max_reply_images], start=1):
                target = (
                    out_dir / "images" / f"{index:02d}_{post.author}_reply{position}.jpg"
                )
                try:
                    reply_paths.append(str(fetch_image(url, target)))
                except Exception:
                    continue

        leads.append(
            Lead(
                author=post.author,
                permalink=post.permalink,
                posted_on=post.posted_on,
                claim=post.text,
                money_mentioned=money_in(post.text),
                handles_from_text=extract_handles(post.text, exclude=post.author),
                image_paths=tuple(paths),
                reply_image_paths=tuple(reply_paths),
            )
        )
    return leads


def save_leads(leads: list[Lead], out_dir: Path, query: str, now: datetime) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "leads.json"
    path.write_text(
        json.dumps(
            {
                "query": query,
                "gathered_at": now.isoformat(),
                "leads": [asdict(lead) for lead in leads],
            },
            indent=2,
        )
    )
    return path


def load_leads(out_dir: Path) -> tuple[str, list[Lead]]:
    path = out_dir / "leads.json"
    if not path.exists():
        raise MissingDataError(f"no leads at {path}; run the gather stage first")
    record = json.loads(path.read_text())
    # JSON has no tuple, so every sequence returns as a list. Coerce back, or
    # Lead stops being hashable and comparing a reloaded run to a fresh one
    # fails for reasons that have nothing to do with the data.
    tupled = (
        "money_mentioned",
        "handles_from_text",
        "image_paths",
        "handles_from_images",
        "reply_image_paths",
    )
    return record["query"], [
        Lead(**{k: tuple(v) if k in tupled else v for k, v in item.items()})
        for item in record["leads"]
    ]


def add_image_handles(out_dir: Path, mapping: dict[str, list[str]]) -> list[Lead]:
    """Record handles read out of the screenshots, keyed by permalink."""
    query, leads = load_leads(out_dir)
    updated = [
        Lead(
            **{
                **asdict(lead),
                "handles_from_images": tuple(mapping.get(lead.permalink, ())),
            }
        )
        for lead in leads
    ]
    save_leads(updated, out_dir, query, datetime.now(timezone.utc))
    return updated


def profile_views(views: list[int], hit_threshold: int = 100_000) -> dict:
    """Median, skew and hit-rate. Never the mean alone - see C-001."""
    if not views:
        raise MissingDataError("cannot profile a channel with no long-form videos")
    ordered = sorted(views)
    median = st.median(ordered)
    mean = st.mean(ordered)
    hits = sum(1 for v in ordered if v >= hit_threshold)
    return {
        "n": len(ordered),
        "median": round(median),
        "mean": round(mean),
        "skew": round(mean / max(median, 1), 2),
        "hits": hits,
        "hit_rate": round(100 * hits / len(ordered), 1),
        "min": ordered[0],
        "max": ordered[-1],
        "repeatable": mean / max(median, 1) <= 3
        and 100 * hits / len(ordered) >= 40
        and len(ordered) >= 8,
    }


def write_report(rows: list[dict], leads: list[Lead], out_dir: Path, query: str) -> Path:
    """Claim beside measurement, so the gap between them is visible."""
    checked = {row["handle"].lower() for row in rows}
    unnamed = [
        lead for lead in leads if lead.money_mentioned and not lead.all_handles
    ]
    lines = [
        f"# Threads lead report — {query}",
        "",
        f"- posts gathered: {len(leads)}",
        f"- posts making a monetary claim: {sum(1 for l in leads if l.money_mentioned)}",
        f"- channels named and checked: {len(rows)}",
        f"- monetary claims naming no channel (uncheckable): {len(unnamed)}",
        "",
        "## Verified channels",
        "",
        "| handle | subs | n | median | skew | hit% | repeatable | claim source |",
        "|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in sorted(rows, key=lambda r: -r.get("median", 0)):
        lines.append(
            f"| @{row['handle']} | {row['subs']:,} | {row['n']} | {row['median']:,} | "
            f"{row['skew']} | {row['hit_rate']}% | "
            f"{'yes' if row['repeatable'] else 'no'} | {row['permalink']} |"
        )
    if unnamed:
        lines += ["", "## Uncheckable claims", ""]
        for lead in unnamed:
            lines.append(f"- @{lead.author}: {lead.claim[:150]} — {lead.permalink}")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "report.md"
    path.write_text("\n".join(lines) + "\n")
    return path
