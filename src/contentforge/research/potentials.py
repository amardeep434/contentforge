"""The potentials list: every channel this project has verified, kept.

Lead runs are disposable — `data/leads/` is regenerable and gitignored. This
file is not. It is the accumulated result of every research pass, so a channel
checked once never has to be checked again, and a channel that was rejected
stays rejected with the reason attached.

Keyed on **channel id, never handle.** Handles are renameable and guessing them
has been wrong 4 times out of 4 (C-008); the id is stable and is what the API
actually returns.

Re-running research updates the measurements and `last_checked` while preserving
`first_seen`, `status` and `notes` — the judgement a human added must survive a
refresh, or nobody will bother adding any.
"""

import csv
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

FIELDS = (
    "channel_id",
    "handle",
    "title",
    "subs",
    "n",
    "median",
    "mean",
    "skew",
    "hit_rate",
    "min_views",
    "max_views",
    "repeatable",
    "views_per_sub",
    "verdict",
    "verdict_reason",
    "criteria_version",
    "status",
    "notes",
    "source",
    "first_seen",
    "last_checked",
)

# `verdict` is written by analytics and refreshed on every run. `status` is the
# human override and is never touched by machinery - empty means "no human has
# an opinion". Conflating the two meant analytics could not record a decision
# without destroying someone's note, which is why they are separate columns.
NO_HUMAN_OPINION = ""
#: A human override must use the *same vocabulary* as an analytics verdict, or
#: `standing` returns a value nothing counts. Writing "watching" where the
#: machine writes "watch" silently dropped 4 channels out of every summary.
VALID_STATUS = ("", "exemplar", "watch", "reject")


def validate_status(status: str) -> str:
    if status not in VALID_STATUS:
        raise ValueError(
            f"status {status!r} is not one of {VALID_STATUS}; human overrides must "
            "use the same vocabulary as analytics verdicts"
        )
    return status


@dataclass(frozen=True)
class Potential:
    channel_id: str
    handle: str
    title: str
    subs: int
    n: int
    median: int
    mean: int
    skew: float
    hit_rate: float
    min_views: int
    max_views: int
    repeatable: bool
    views_per_sub: float
    verdict: str
    verdict_reason: str
    criteria_version: str
    status: str
    notes: str
    source: str
    first_seen: str
    last_checked: str

    @property
    def standing(self) -> str:
        """The human's call if there is one, otherwise the machine's."""
        return self.status or self.verdict

    @property
    def label(self) -> str:
        """How to refer to this channel in output.

        Rows seeded from scans carry a title but no handle, because the scan
        endpoints do not return one. Printing a title as `@title` would invent a
        handle that does not resolve - which is C-008 with extra steps.
        """
        return f"@{self.handle}" if self.handle else self.title

    @property
    def reachable(self) -> bool:
        """Small enough that its numbers say something about a new channel.

        A 1M-subscriber channel draws views from its base and its standing, so
        its performance cannot be extrapolated to a channel starting from zero.
        """
        return self.subs < 80_000


def from_profile(
    profile: dict, now: datetime, source: str = "", verdict=None
) -> Potential:
    """Build a row from a measurement, optionally with an analytics verdict."""
    subs = max(int(profile["subs"]), 1)
    stamp = now.date().isoformat()
    return Potential(
        channel_id=profile["channel_id"],
        handle=profile["handle"],
        title=profile.get("title", ""),
        subs=int(profile["subs"]),
        n=int(profile["n"]),
        median=int(profile["median"]),
        mean=int(profile["mean"]),
        skew=float(profile["skew"]),
        hit_rate=float(profile["hit_rate"]),
        min_views=int(profile["min"]),
        max_views=int(profile["max"]),
        repeatable=bool(profile["repeatable"]),
        views_per_sub=round(int(profile["median"]) / subs, 2),
        verdict=verdict.status if verdict else "",
        verdict_reason=verdict.reason if verdict else "",
        criteria_version=verdict.criteria_version if verdict else "",
        status=NO_HUMAN_OPINION,
        notes="",
        source=source,
        first_seen=stamp,
        last_checked=stamp,
    )


def load_potentials(path: Path) -> list[Potential]:
    if not path.exists():
        return []
    rows = []
    for record in csv.DictReader(path.open()):
        rows.append(
            Potential(
                channel_id=record["channel_id"],
                handle=record["handle"],
                title=record["title"],
                subs=int(record["subs"]),
                n=int(record["n"]),
                median=int(record["median"]),
                mean=int(record["mean"]),
                skew=float(record["skew"]),
                hit_rate=float(record["hit_rate"]),
                min_views=int(record["min_views"]),
                max_views=int(record["max_views"]),
                repeatable=record["repeatable"] == "True",
                views_per_sub=float(record["views_per_sub"]),
                verdict=record.get("verdict", ""),
                verdict_reason=record.get("verdict_reason", ""),
                criteria_version=record.get("criteria_version", ""),
                status=record["status"],
                notes=record["notes"],
                source=record["source"],
                first_seen=record["first_seen"],
                last_checked=record["last_checked"],
            )
        )
    return rows


def upsert(existing: list[Potential], incoming: list[Potential]) -> list[Potential]:
    """Merge new measurements into the list without losing human judgement.

    Returns a new list; nothing is mutated. An existing row keeps its
    `first_seen`, `status` and `notes` and takes every measured field from the
    incoming row.
    """
    by_id = {row.channel_id: row for row in existing}
    merged = list(existing)
    # Incoming can itself contain the same channel twice - two scans in one
    # seed, or a channel named by two different posts. Later wins.
    deduped = list({row.channel_id: row for row in incoming}.values())
    for fresh in deduped:
        previous = by_id.get(fresh.channel_id)
        if previous is None:
            merged.append(fresh)
            continue
        updated = replace(
            fresh,
            first_seen=previous.first_seen,
            status=previous.status,
            notes=previous.notes,
            # keep the earliest attribution; later sightings add nothing
            source=previous.source or fresh.source,
        )
        merged[merged.index(previous)] = updated
    return merged


def save_potentials(path: Path, rows: list[Potential]) -> Path:
    """Write sorted by median, so the interesting rows are at the top."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows, key=lambda r: -r.median)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in ordered:
            writer.writerow({field: getattr(row, field) for field in FIELDS})
    return path


def summarise(rows: list[Potential]) -> str:
    judged = [r for r in rows if r.verdict]
    exemplars = [r for r in judged if r.standing == "exemplar"]
    watching = [r for r in judged if r.standing == "watch"]
    lines = [
        f"{len(rows)} channels tracked, {len(judged)} judged",
        f"  exemplar (repeatable and reachable): {len(exemplars)}",
        f"  watch (repeatable, too large):       {len(watching)}",
        f"  reject:                              "
        f"{sum(1 for r in judged if r.standing == 'reject')}",
    ]
    if exemplars:
        lines.append("")
        lines.append("  exemplars:")
        for row in sorted(exemplars, key=lambda r: -r.views_per_sub):
            lines.append(
                f"    {row.label:<26} {row.subs:>8,} subs  "
                f"median {row.median:>9,}  {row.views_per_sub:>5.1f} views/sub"
            )
            lines.append(f"      {row.verdict_reason}")
    return "\n".join(lines)
