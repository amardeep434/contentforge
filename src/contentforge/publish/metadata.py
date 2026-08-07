"""Title, description and tags for a finished video.

Generated from the script, not guessed, and clamped to YouTube's own limits
before anything is uploaded - a title over 100 characters or a tag set over 500
is rejected at insert time, twenty minutes after the render, which is the worst
place to discover it. The limits are enforced here instead.

The description carries the source URLs the script was grounded in. That is not
decoration: it is the provenance trail this whole project is built on, visible
to the viewer, and the honest answer to "where did this come from".

Parsing is separated from the LLM call, so the awkward part - a model that
returns prose around its JSON, or a title with a newline in it - is unit tested
without a network.
"""

import json
import re
from dataclasses import dataclass, field

from contentforge.errors import MissingDataError
from contentforge.providers.llm import LLMClient

#: YouTube's hard limits. Exceeding any is a rejected upload, not a warning.
MAX_TITLE = 100
MAX_DESCRIPTION = 5000
MAX_TAGS_TOTAL = 500

#: A default category id; 27 is "Education". Overridable per upload.
DEFAULT_CATEGORY = "27"

SYSTEM = """You write YouTube metadata for a long-form business-explainer video,
modelled on the title and description pattern proven to work in this niche.

The pattern, measured across the channel's best-performing videos:
- Titles follow "The Economics of Owning a [X]", where X is a concrete business
  the viewer has plausibly stood inside - a gym, a car dealership, a shopping
  mall. The winners are always tangible, everyday businesses, never abstract
  ones. Keep the title in that frame unless the script is clearly not about
  owning a business, in which case name the thing plainly.
- Descriptions open with one sentence restating the video's central reframe,
  then two or three short paragraphs of what it covers, in plain language.

Return a JSON object with:
- "title": under 100 characters, in the pattern above. No clickbait punctuation
  spam, no ALL CAPS words.
- "description": first line restates the hook, then two or three short
  paragraphs. Do not invent facts not in the script. Never claim personal
  experience.
- "tags": 8 to 15 short lowercase search phrases, as a JSON array.
- "thumb_headline": TWO to FOUR words for the thumbnail - the blunt hook, not
  the title. e.g. "WHERE THE MONEY GOES", "IT IS NOT A GYM". Never more than
  four words; it has to be read at a glance.

Return only the JSON object. No prose, no code fence.
"""

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


#: A thumbnail hook longer than this cannot be read at a glance; kept in sync
#: with the thumbnail renderer's own limit.
MAX_THUMB_WORDS = 4


@dataclass(frozen=True)
class Metadata:
    """Everything the upload needs except the file itself."""

    title: str
    description: str
    tags: tuple[str, ...] = field(default_factory=tuple)
    category_id: str = DEFAULT_CATEGORY
    thumb_headline: str = ""


def _clean(raw: str) -> str:
    stripped = _FENCE.sub("", raw).strip()
    start, end = stripped.find("{"), stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise MissingDataError(f"no JSON object in the metadata response: {stripped[:160]!r}")
    return stripped[start : end + 1]


def _clamp_tags(tags: list[str]) -> tuple[str, ...]:
    """Drop tags once the running total would exceed YouTube's 500-char budget.

    YouTube counts the joined length, so a long tail of tags silently truncates
    the list at insert time. Dropping the overflow here keeps the kept tags
    whole rather than letting the API cut one in half.
    """
    kept, total = [], 0
    for tag in tags:
        clean = " ".join(str(tag).split()).lower()
        if not clean:
            continue
        # +1 approximates the separator YouTube counts between tags.
        if total + len(clean) + 1 > MAX_TAGS_TOTAL:
            break
        kept.append(clean)
        total += len(clean) + 1
    return tuple(kept)


def parse_metadata(raw: str, sources: list | None = None) -> Metadata:
    """Validate a model response into publishable metadata."""
    try:
        data = json.loads(_clean(raw))
    except json.JSONDecodeError as error:
        raise MissingDataError(f"metadata is not valid JSON: {error}") from None
    if not isinstance(data, dict):
        raise MissingDataError("metadata must be a JSON object")

    title = " ".join(str(data.get("title", "")).split())
    if not title:
        raise MissingDataError("metadata has no title")
    if len(title) > MAX_TITLE:
        raise MissingDataError(
            f"title is {len(title)} characters; YouTube rejects over {MAX_TITLE}"
        )

    description = str(data.get("description", "")).strip()
    if not description:
        raise MissingDataError("metadata has no description")
    description = with_sources(description, sources or [])
    if len(description) > MAX_DESCRIPTION:
        raise MissingDataError(
            f"description is {len(description)} characters; over {MAX_DESCRIPTION}"
        )

    tags = data.get("tags") or []
    if not isinstance(tags, list):
        raise MissingDataError("tags must be a JSON array")

    return Metadata(title=title, description=description, tags=_clamp_tags(tags),
                    thumb_headline=_thumb_headline(data.get("thumb_headline"), title))


def _thumb_headline(raw, title: str) -> str:
    """A short thumbnail hook, always at most MAX_THUMB_WORDS words.

    Falls back to the first few words of the title when the model omits it or
    over-runs, so the thumbnail stage never receives an unusable headline and
    never crashes a finished render over it.
    """
    words = " ".join(str(raw or "").split()).split()
    if not words or len(words) > MAX_THUMB_WORDS:
        words = title.split()[:MAX_THUMB_WORDS]
    return " ".join(words)


def with_sources(description: str, sources: list) -> str:
    """Append the provenance trail the script was grounded in."""
    urls = [getattr(s, "url", None) or s.get("url") for s in sources
            if getattr(s, "url", None) or (isinstance(s, dict) and s.get("url"))]
    if not urls:
        return description
    lines = "\n".join(f"- {url}" for url in urls)
    return f"{description}\n\nSources:\n{lines}"


def generate_metadata(client: LLMClient, script: str, sources: list | None = None,
                      title_format: str | None = None) -> Metadata:
    """Metadata from the script, grounded and clamped to YouTube's limits."""
    if not script.strip():
        raise MissingDataError("no script to derive metadata from")
    user = f"Script:\n\n{script.strip()[:6000]}"
    system = SYSTEM if title_format is None else SYSTEM.replace(
        "The Economics of Owning a [X]", title_format.replace("{subject}", "[X]")
    )
    return parse_metadata(client.complete(system, user, max_tokens=1200), sources)
