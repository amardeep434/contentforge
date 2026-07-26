"""Niche discovery: seed queries in, deduplicated channel set out.

Channels ranking for several queries in the same niche are counted once. Without
dedupe a broadly-ranking channel would inflate the competitor count for every
query it appears in, making the niche look more saturated than it is.
"""

from dataclasses import dataclass

from contentforge.errors import MissingDataError
from contentforge.providers.quota import QuotaLedger
from contentforge.providers.youtube_api import YouTubeClient
from contentforge.provenance import Provenance


@dataclass(frozen=True)
class NicheCandidate:
    niche: str
    queries: tuple[str, ...]
    channel_ids: tuple[str, ...]
    provenance: Provenance


def discover_niche(
    client: YouTubeClient, niche: str, queries: list[str], ledger: QuotaLedger
) -> tuple[NicheCandidate, QuotaLedger]:
    if not queries:
        raise MissingDataError(f"no seed queries for niche {niche!r}")

    seen: list[str] = []
    current = ledger
    first_provenance: Provenance | None = None

    for query in queries:
        refs, current = client.search_channels(query, current)
        if first_provenance is None:
            first_provenance = refs[0].provenance
        for ref in refs:
            if ref.channel_id not in seen:
                seen.append(ref.channel_id)

    if first_provenance is None:
        raise MissingDataError(f"no search provenance captured for niche {niche!r}")

    candidate = NicheCandidate(
        niche=niche,
        queries=tuple(queries),
        channel_ids=tuple(seen),
        provenance=first_provenance,
    )
    return candidate, current
