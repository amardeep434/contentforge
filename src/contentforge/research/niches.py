"""Niche table: revenue and monetization constraints, hand-sourced.

RPM drives every ranking decision and an LLM will invent plausible figures
readily, so each row carries a source URL and retrieval date. Published figures
disagree materially between sources, so a row names the single source it came
from rather than blending several.

memberships_available exists because of Made for Kids. COPPA bars behavioural
tracking on under-13 content, so only contextual ads serve, and Super Thanks
and Channel Memberships are disabled at platform level — removing the Tier 1
revenue path (500 subscribers) entirely. The scorer penalises restricted niches
rather than the operator arguing about it.
"""

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from contentforge.errors import MissingDataError
from contentforge.provenance import Fact, Provenance

# Assumption, not a live rate. The ranking is comparative, so a stale rate
# shifts every INR row equally and does not reorder results.
INR_PER_USD = 88.0


@dataclass(frozen=True)
class Niche:
    name: str
    geography: str
    rpm_low: float
    rpm_high: float
    currency: str
    memberships_available: bool
    seed_queries: tuple[str, ...]
    provenance: Provenance


def load_niches(path: Path) -> dict[tuple[str, str], Niche]:
    table: dict[tuple[str, str], Niche] = {}
    with open(path, newline="", encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            provenance = Provenance(
                source_url=record["source_url"],
                response_id=f"niches:{record['niche']}:{record['geography']}",
                retrieved_at=datetime.fromisoformat(record["retrieved_at"]).replace(
                    tzinfo=timezone.utc
                ),
            )
            niche = Niche(
                name=record["niche"],
                geography=record["geography"],
                rpm_low=float(record["rpm_low"]),
                rpm_high=float(record["rpm_high"]),
                currency=record["currency"],
                memberships_available=(
                    record["memberships_available"].strip().lower() == "true"
                ),
                seed_queries=tuple(
                    query.strip()
                    for query in record["seed_queries"].split("|")
                    if query.strip()
                ),
                provenance=provenance,
            )
            table[(niche.name, niche.geography)] = niche

    if not table:
        raise MissingDataError(f"niche table at {path} is empty")
    return table


def rpm_midpoint_usd(niche: Niche) -> Fact:
    """Midpoint RPM in USD.

    An unsupported currency raises rather than passing the figure through
    unconverted, which would silently inflate that niche's rank.
    """
    midpoint = (niche.rpm_low + niche.rpm_high) / 2
    if niche.currency == "INR":
        return Fact(value=midpoint / INR_PER_USD, provenance=niche.provenance)
    if niche.currency == "USD":
        return Fact(value=midpoint, provenance=niche.provenance)
    raise MissingDataError(
        f"unsupported currency {niche.currency!r} for "
        f"{niche.name!r}/{niche.geography!r}"
    )
