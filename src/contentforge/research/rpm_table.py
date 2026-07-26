"""RPM lookup, sourced by hand.

RPM drives every ranking decision, and an LLM will invent plausible figures
readily. So this is a checked-in CSV with a source URL and retrieval date per
row, updated deliberately. Wrong-but-cited beats confident-and-fabricated,
because a cited figure can be checked and a fabricated one cannot.
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
class RpmRow:
    niche: str
    geography: str
    rpm_low: float
    rpm_high: float
    currency: str
    provenance: Provenance


def load_rpm_table(path: Path) -> dict[tuple[str, str], RpmRow]:
    table: dict[tuple[str, str], RpmRow] = {}
    with open(path, newline="", encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            provenance = Provenance(
                source_url=record["source_url"],
                response_id=f"rpm_table:{record['niche']}:{record['geography']}",
                retrieved_at=datetime.fromisoformat(record["retrieved_at"]).replace(
                    tzinfo=timezone.utc
                ),
            )
            row = RpmRow(
                niche=record["niche"],
                geography=record["geography"],
                rpm_low=float(record["rpm_low"]),
                rpm_high=float(record["rpm_high"]),
                currency=record["currency"],
                provenance=provenance,
            )
            table[(row.niche, row.geography)] = row
    return table


def rpm_midpoint_usd(
    table: dict[tuple[str, str], RpmRow], niche: str, geography: str
) -> Fact:
    """Midpoint RPM in USD for a niche/geography pair.

    A missing pair raises rather than falling back to a nearby row or a global
    average — a silently substituted RPM would reorder the whole ranking.
    """
    row = table.get((niche, geography))
    if row is None:
        raise MissingDataError(
            f"no RPM row for ({niche!r}, {geography!r}); "
            "add a sourced row to data/rpm_table.csv"
        )
    midpoint = (row.rpm_low + row.rpm_high) / 2
    if row.currency == "INR":
        return Fact(value=midpoint / INR_PER_USD, provenance=row.provenance)
    if row.currency == "USD":
        return Fact(value=midpoint, provenance=row.provenance)
    raise MissingDataError(
        f"unsupported currency {row.currency!r} for ({niche!r}, {geography!r})"
    )
