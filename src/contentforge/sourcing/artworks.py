"""Public-domain artworks from the Metropolitan Museum's open-access collection.

The visual asset for an art-history video is free and legal *only* when the
artwork itself is public domain. Faithful photographic reproductions of
public-domain 2D works carry no new copyright — *Bridgeman v. Corel* in the US,
Article 14 of the EU DSM Directive in Europe (C-033) — but that says nothing
about a painting still in copyright.

Two independent checks must both pass, and each fails closed:

  1. the museum's `isPublicDomain` flag is explicitly true
  2. the artist's death year is known *and* clears life + 70

Two, because the first is someone else's judgement about their jurisdiction and
the second is arithmetic we can audit. A record missing either is dropped, never
defaulted — "we could not establish it" must not become "it is probably fine".

**Why the Met and not the Art Institute of Chicago.** AIC was tried first and its
metadata is good, but its IIIF image host sits behind a Cloudflare challenge that
returns an HTML interstitial instead of a JPEG, for any user agent tried. An
image source whose images cannot be fetched is not a source. The Met returns
`artistEndDate` as a structured field rather than one to be parsed out of a
display string, and its images download directly.

Cost: two calls per search — the API returns object ids, then each object is
fetched. No key, no quota.
"""

import json
import re
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from contentforge.errors import MissingDataError

SEARCH = "https://collectionapi.metmuseum.org/public/collection/v1/search"
OBJECT = "https://collectionapi.metmuseum.org/public/collection/v1/objects"

#: Copyright expires at the end of the 70th year after death, so an artist who
#: died in 1956 is not clear until 2027. Compared with `>`, never `>=`.
COPYRIGHT_TERM_YEARS = 70

#: Fallback only: "Paul Cezanne (French, 1839–1906)". Used when artistEndDate is
#: absent. A trailing year counts as a death year only when a birth year
#: precedes it, so "born 1955" is not misread.
_LIFESPAN = re.compile(r"\b(\d{4})\s*[–—-]\s*(\d{4})\b")


@dataclass(frozen=True)
class Artwork:
    title: str
    artist: str
    year: str
    image_url: str
    source: str
    license: str
    credit_line: str
    retrieved_at: datetime


def death_year_from(artist_display: str) -> int | None:
    """The death year in a lifespan string, or None when there isn't one."""
    match = _LIFESPAN.search(artist_display or "")
    return int(match.group(2)) if match else None


def death_year_of(record: dict) -> int | None:
    """Prefer the museum's structured field; fall back to parsing a string.

    `artistEndDate` is "" for a living artist and sometimes "0" for an unknown
    one — neither is a death year, and treating "0" as one would clear every
    such artwork as ancient.
    """
    raw = str(record.get("artistEndDate") or "").strip()
    if re.fullmatch(r"-?\d{3,4}", raw) and int(raw) > 0:
        return int(raw)
    return death_year_from(record.get("artistDisplayName", ""))


def assert_public_domain(death_year: int | None, now: datetime) -> None:
    """Raise unless the artist's copyright has demonstrably expired."""
    if death_year is None:
        raise MissingDataError(
            "cannot establish the artist's death year, so public-domain status "
            "cannot be verified; the artwork is skipped rather than assumed safe"
        )
    clear_from = death_year + COPYRIGHT_TERM_YEARS
    if now.year <= clear_from:
        raise MissingDataError(
            f"artist died {death_year}; copyright runs to the end of {clear_from}, "
            f"so this is not public domain in {now.year}"
        )


def http_get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "contentforge/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def _fold(text: str) -> str:
    """Casefold and strip accents, so "Cézanne" matches a query of "Cezanne"."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def artist_matches(record: dict, query: str) -> bool:
    """True when the artwork is actually by the artist searched for.

    The Met's free-text search matches any field, so a query for "Klimt"
    happily returns a Guido Reni. Silently accepting those would put another
    painter's work in the video - worse than returning nothing, because it
    looks like success.
    """
    artist = _fold(record.get("artistDisplayName") or "")
    if not artist:
        return False
    # Surname is the discriminating token; "Paul Cezanne" must match a query of
    # "Cezanne" and vice versa. Accents are stripped because the museum writes
    # "Cézanne" and nobody types it that way.
    tokens = [t for t in re.split(r"[^\w]+", _fold(query)) if len(t) > 2]
    return any(token in artist for token in tokens) if tokens else False


def parse_artwork(record: dict, now: datetime) -> Artwork | None:
    """One artwork, or None when it fails either licence check."""
    # Explicit `is not True`: a missing flag is not a false one, and a truthy
    # string is not a boolean.
    if record.get("isPublicDomain") is not True:
        return None
    if not record.get("primaryImage"):
        return None
    try:
        assert_public_domain(death_year_of(record), now)
    except MissingDataError:
        return None
    return Artwork(
        title=record.get("title") or "",
        artist=record.get("artistDisplayName") or "",
        year=record.get("objectDate") or "",
        image_url=record["primaryImage"],
        source=record.get("objectURL") or "",
        license="public domain (The Metropolitan Museum of Art, Open Access)",
        # Retained even though copyright does not compel attribution: museums
        # impose contractual terms where copyright has expired, and this field
        # is the only record of them (C-033).
        credit_line=record.get("creditLine") or "",
        retrieved_at=now,
    )


def search_artworks(
    query: str,
    transport: Callable[[str], str] = http_get,
    now: datetime | None = None,
    limit: int = 12,
    strict: bool = True,
) -> list[Artwork]:
    """Search, then fetch each object until `limit` artworks pass both checks."""
    now = now or datetime.now(timezone.utc)
    # The Met documents an `artistOrCulture=true` flag to restrict matching to
    # the artist field. It returns 0 results for every artist tried - Cezanne,
    # Monet, Degas - while the same query without it returns ~170. So the
    # filtering is done here instead, by artist_matches.
    url = f"{SEARCH}?q={urllib.parse.quote(query)}&hasImages=true"
    try:
        body = transport(url)
    except MissingDataError:
        raise
    except Exception as error:
        raise MissingDataError(
            f"artwork search failed for {query!r}: {type(error).__name__}"
        ) from None
    try:
        object_ids = json.loads(body).get("objectIDs") or []
    except json.JSONDecodeError:
        raise MissingDataError("artwork search returned no parseable JSON") from None

    artworks: list[Artwork] = []
    # Bounded: each id costs a request, and a broad query returns hundreds.
    for object_id in object_ids[: limit * 4]:
        if len(artworks) >= limit:
            break
        try:
            record = json.loads(transport(f"{OBJECT}/{object_id}"))
        except Exception:
            # One unreachable object must not lose the whole search.
            continue
        if not artist_matches(record, query):
            continue
        artwork = parse_artwork(record, now)
        if artwork:
            artworks.append(artwork)

    if strict and not artworks:
        raise MissingDataError(
            f"no public-domain artworks by {query!r} with images survived the "
            f"licence and artist checks. The collection may not hold this "
            f"artist - that is an answer, not a reason to substitute another."
        )
    return artworks


def survey_artists(
    names: list[str],
    transport: Callable[[str], str] = http_get,
    now: datetime | None = None,
    limit: int = 12,
) -> dict[str, int]:
    """How many usable artworks each candidate artist actually has.

    Open-access coverage varies enormously by artist and is not predictable from
    fame or death date: the Met holds Cezanne and Degas with images, but its
    Monet records are `isPublicDomain: False` with no image at all even though he
    died in 1926. Picking a subject before checking is how a video gets planned
    around artworks that cannot legally or practically be used.

    Run this before committing to a video subject.
    """
    counts: dict[str, int] = {}
    for name in names:
        try:
            counts[name] = len(
                search_artworks(
                    name, transport=transport, now=now, limit=limit, strict=False
                )
            )
        except MissingDataError:
            counts[name] = 0
    return counts
