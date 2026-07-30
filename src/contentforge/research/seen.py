"""What happened to every lead, kept across runs.

The potentials list holds channels that verified. This holds everything else —
the posts that named nothing, the ones whose screenshots were already read and
found empty, the lookups that failed. Without it a research run has no memory:
it re-gathers the same posts, re-downloads the same screenshots, and a human
re-reads images they already read and already learned nothing from.

It also keeps the denominator. Claims like "9 monetary claims, 0 checkable"
(C-039) are only meaningful if the uncheckable ones are counted somewhere that
survives the run, and `data/leads/` is gitignored and regenerable.

Text only — permalinks and short excerpts. The screenshots stay out of git:
they are large and they are someone else's content.
"""

import csv
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

FIELDS = (
    "permalink",
    "author",
    "posted_on",
    "outcome",
    "handles",
    "money",
    "claim",
    "first_seen",
    "last_seen",
)

#: A lead's fate. `unread` is the honest default - it means the screenshots were
#: downloaded but nobody has looked at them, which is not the same as looking
#: and finding nothing (`no_channel`).
UNREAD = "unread"
NO_CHANNEL = "no_channel"
VERIFIED = "verified"
LOOKUP_FAILED = "lookup_failed"
OUTCOMES = (UNREAD, NO_CHANNEL, VERIFIED, LOOKUP_FAILED)

#: Outcomes that mean "done with this post". An `unread` post is worth
#: re-offering; a resolved one is not.
SETTLED = (NO_CHANNEL, VERIFIED, LOOKUP_FAILED)


@dataclass(frozen=True)
class SeenPost:
    permalink: str
    author: str
    posted_on: str
    outcome: str
    handles: str
    money: str
    claim: str
    first_seen: str
    last_seen: str

    @property
    def settled(self) -> bool:
        return self.outcome in SETTLED


def from_lead(lead, now: datetime) -> SeenPost:
    stamp = now.date().isoformat()
    return SeenPost(
        permalink=lead.permalink,
        author=lead.author,
        posted_on=lead.posted_on,
        outcome=NO_CHANNEL if lead.handles_from_images else UNREAD,
        handles=" ".join(lead.all_handles),
        money=" ".join(lead.money_mentioned),
        claim=lead.claim[:200],
        first_seen=stamp,
        last_seen=stamp,
    )


def load_seen(path: Path) -> list[SeenPost]:
    if not path.exists():
        return []
    return [SeenPost(**record) for record in csv.DictReader(path.open())]


def upsert_seen(existing: list[SeenPost], incoming: list[SeenPost]) -> list[SeenPost]:
    """Merge, keyed on permalink, without downgrading a settled outcome.

    A re-gather sees the same post again and would naively write it back as
    `unread`, erasing the fact that someone already read its screenshots. The
    outcome only ever moves forward.
    """
    by_link = {row.permalink: row for row in existing}
    merged = list(existing)
    deduped = list({row.permalink: row for row in incoming}.values())
    for fresh in deduped:
        previous = by_link.get(fresh.permalink)
        if previous is None:
            merged.append(fresh)
            continue
        outcome = previous.outcome if previous.settled else fresh.outcome
        handles = fresh.handles or previous.handles
        merged[merged.index(previous)] = replace(
            fresh,
            outcome=outcome,
            handles=handles,
            first_seen=previous.first_seen,
        )
    return merged


def mark(
    rows: list[SeenPost], permalink: str, outcome: str, handles: str = ""
) -> list[SeenPost]:
    """Set one post's outcome, returning a new list."""
    if outcome not in OUTCOMES:
        raise ValueError(f"unknown outcome {outcome!r}; expected one of {OUTCOMES}")
    return [
        replace(row, outcome=outcome, handles=handles or row.handles)
        if row.permalink == permalink
        else row
        for row in rows
    ]


def save_seen(path: Path, rows: list[SeenPost]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in sorted(rows, key=lambda r: r.first_seen):
            writer.writerow({field: getattr(row, field) for field in FIELDS})
    return path


def unsettled(rows: list[SeenPost]) -> list[SeenPost]:
    """Posts whose screenshots still need reading."""
    return [row for row in rows if not row.settled]


def summarise_seen(rows: list[SeenPost]) -> str:
    counts = {outcome: 0 for outcome in OUTCOMES}
    for row in rows:
        counts[row.outcome] = counts.get(row.outcome, 0) + 1
    with_money = [r for r in rows if r.money]
    uncheckable = [r for r in with_money if r.outcome == NO_CHANNEL]
    lines = [
        f"{len(rows)} posts seen across all runs",
        f"  verified a channel:      {counts[VERIFIED]}",
        f"  read, named no channel:  {counts[NO_CHANNEL]}",
        f"  lookup failed:           {counts[LOOKUP_FAILED]}",
        f"  screenshots unread:      {counts[UNREAD]}",
    ]
    if with_money:
        share = 100 * len(uncheckable) / len(with_money)
        lines.append("")
        lines.append(
            f"  posts claiming money: {len(with_money)}, of which "
            f"{len(uncheckable)} named no channel ({share:.0f}% uncheckable)"
        )
    return "\n".join(lines)
