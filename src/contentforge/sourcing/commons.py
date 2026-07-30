"""Public-domain artworks from Wikimedia Commons.

The second source, required because one museum is not enough: the Met holds no
open-access Monet, Renoir or Klimt at all, and coverage does not follow fame or
death date (C-045). Commons is unaffected by any single institution's
digitisation policy.

Two gates, both of which real results fail:

**Licence.** Commons hosts CC-BY and CC-BY-SA alongside public domain. A search
for Monet returns `File:Claude Monet Painting in his Studio` under `cc-by-4.0`.
Only `pd` / `cc0` are accepted here — an attribution-required licence is a
different legal obligation, not a slightly weaker version of the same one.

**Authorship.** `extmetadata.Artist` is the *photographer or uploader*, not the
painter — for `Le Pont d'Argenteuil` it names the Commons user who photographed
it. Relying on it would misattribute every work. Authorship is instead taken
from the file's categories, and the category must say *paintings **by*** the
artist: a search for Monet also returns Édouard Manet's portrait *of* Monet,
which sits in a category containing "Claude Monet" and is by someone else.

Namespace 6 is the File namespace; without `gsrnamespace=6` the search returns
articles rather than images.
"""

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Callable

from contentforge.errors import MissingDataError
from contentforge.sourcing.artworks import Artwork, assert_public_domain

API = "https://commons.wikimedia.org/w/api.php"

#: Commons requires a descriptive User-Agent and throttles generic ones.
UA = "contentforge/0.1 (research; contact via repository)"

#: Only these carry no attribution obligation. CC-BY and CC-BY-SA are excluded
#: deliberately: they are usable, but under terms this pipeline does not track.
FREE_LICENSES = ("pd", "cc0")

#: "Paintings by Claude Monet", "Featured pictures of paintings by Claude Monet",
#: "Details of paintings by Claude Monet" — all authored by the artist.
#: "Portrait de Claude Monet ... par Édouard Manet" — not.
_BY_ARTIST = "{kind} by {artist}"
_KINDS = ("paintings", "drawings", "prints", "works", "sketches", "artworks")

_TAGS = re.compile(r"<[^>]+>")
#: Commons splices Wikidata structured-data markers into ObjectName, e.g.
#: 'At Petit-Gennevillierslabel QS:Lfr,"Au Petit-Gennevilliers"'. These reach the
#: screen as a chapter title, so they are cut at the first marker.
_QS_MARKER = re.compile(r"(label|title)\s+QS:.*$", re.S)


def _text(extmetadata: dict, key: str) -> str:
    return _TAGS.sub("", str((extmetadata.get(key) or {}).get("value") or "")).strip()


def clean_title(raw: str) -> str:
    """Strip Wikidata structured-data markers spliced into a title."""
    return _QS_MARKER.sub("", raw).strip().strip(",;-").strip()


def is_free_license(extmetadata: dict) -> bool:
    """True only for public domain or CC0."""
    license_id = _text(extmetadata, "License").lower()
    if license_id in FREE_LICENSES:
        return True
    # Some files carry no License id but a plain "Public domain" short name.
    return _text(extmetadata, "LicenseShortName").lower().startswith("public domain")


def by_artist(categories: list[str], artist: str) -> bool:
    """True when a category attributes the work *to* the artist.

    Merely containing the artist's name is not enough — that also matches a
    portrait of them painted by somebody else.
    """
    folded = [c.casefold() for c in categories]
    wanted = [_BY_ARTIST.format(kind=k, artist=artist.casefold()) for k in _KINDS]
    return any(w in c for c in folded for w in wanted)


def http_get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def search_url(artist: str, limit: int) -> str:
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": f"{artist} painting",
        # File namespace. Without it the search returns articles, not images.
        "gsrnamespace": "6",
        "gsrlimit": str(limit),
        "prop": "imageinfo|categories",
        "cllimit": "max",
        "iiprop": "url|extmetadata",
        "iiurlwidth": "1600",
    }
    return f"{API}?{urllib.parse.urlencode(params)}"


def parse_commons(
    body: str, artist: str, now: datetime, death_year: int | None = None
) -> list[Artwork]:
    try:
        pages = (json.loads(body).get("query") or {}).get("pages") or {}
    except json.JSONDecodeError:
        raise MissingDataError("Commons returned no parseable JSON") from None

    artworks: list[Artwork] = []
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        extmetadata = info.get("extmetadata") or {}
        if not is_free_license(extmetadata):
            continue
        categories = [
            c.get("title", "").replace("Category:", "")
            for c in (page.get("categories") or [])
        ]
        if not by_artist(categories, artist):
            continue
        if death_year is not None:
            try:
                assert_public_domain(death_year, now)
            except MissingDataError:
                continue
        url = info.get("thumburl") or info.get("url")
        if not url:
            continue
        artworks.append(
            Artwork(
                title=clean_title(_text(extmetadata, "ObjectName"))
                or clean_title(page.get("title", "").replace("File:", "")),
                artist=artist,
                year=_text(extmetadata, "DateTimeOriginal"),
                image_url=url,
                source="https://commons.wikimedia.org/wiki/"
                + urllib.parse.quote(page.get("title", "")),
                license=_text(extmetadata, "LicenseShortName") or "public domain",
                credit_line=_text(extmetadata, "Credit"),
                retrieved_at=now,
            )
        )
    return artworks


def search_commons(
    artist: str,
    transport: Callable[[str], str] = http_get,
    now: datetime | None = None,
    limit: int = 40,
    death_year: int | None = None,
    strict: bool = True,
) -> list[Artwork]:
    now = now or datetime.now(timezone.utc)
    try:
        body = transport(search_url(artist, limit))
    except MissingDataError:
        raise
    except Exception as error:
        raise MissingDataError(
            f"Commons search failed for {artist!r}: {type(error).__name__}"
        ) from None
    artworks = parse_commons(body, artist, now, death_year)
    if strict and not artworks:
        raise MissingDataError(
            f"no freely-licensed works attributed to {artist!r} on Commons. "
            "Rendering with no visuals is not a fallback."
        )
    return artworks
