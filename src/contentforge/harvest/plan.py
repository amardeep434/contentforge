from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from contentforge.errors import MissingDataError

_NONWORD = re.compile(r"[^a-z0-9]+")
_log = logging.getLogger(__name__)


def slugify(title: str) -> str:
    return _NONWORD.sub("-", title.lower()).strip("-")


@dataclass(frozen=True)
class HarvestEntry:
    slug: str
    topic: str
    video_id: str
    url: str
    title: str


def build_plan(client, channel: str, ledger, limit: int, on_ledger=None):
    """Resolve a channel (a UC… id used directly, anything else treated as an
    @handle) and return (entries, ledger): one HarvestEntry per recent upload,
    topic = title, slug = slugify(title). The quota ledger is threaded through
    every API call and returned so the caller can persist it.

    If `on_ledger` is given, it's called with the latest ledger after each API
    call completes, so a caller can capture partial spend even if a later call
    in this function raises (e.g. MissingDataError for an empty channel).

    NOTE: `get_videos` silently drops videos with no duration (live/upcoming) and
    `VideoRecord` carries no description, so `entries` may be shorter than `limit`
    and only the title is available (which is all harvest needs).
    """
    if channel.startswith("UC") and len(channel) == 24:
        channel_id = channel
    else:
        facts, ledger = client.channel_by_handle(channel.lstrip("@"), ledger)
        if on_ledger:
            on_ledger(ledger)
        channel_id = facts.channel_id

    if limit > 50:
        _log.warning("harvest limit %d capped at 50 (single page)", limit)

    uploads, ledger = client.get_uploads_playlists([channel_id], ledger)
    if on_ledger:
        on_ledger(ledger)
    playlist_id = uploads[channel_id]
    video_ids, ledger = client.get_playlist_video_ids(playlist_id, ledger, max_videos=limit)
    if on_ledger:
        on_ledger(ledger)
    if not video_ids:
        raise MissingDataError(f"no videos found for channel {channel!r}")
    records, ledger = client.get_videos(video_ids, ledger)
    if on_ledger:
        on_ledger(ledger)

    seen: dict[str, int] = {}
    entries = []
    for r in records:
        base = slugify(r.title) or r.video_id          # empty/non-ASCII title fallback
        n = seen.get(base, 0) + 1
        seen[base] = n
        slug = base if n == 1 else f"{base}-{n}"        # -2, -3, ...
        entries.append(
            HarvestEntry(
                slug=slug,
                topic=r.title,
                video_id=r.video_id,
                url=f"https://www.youtube.com/watch?v={r.video_id}",
                title=r.title,
            )
        )

    if not entries:
        raise MissingDataError(
            f"no usable videos for channel {channel!r} "
            f"({len(video_ids)} found, all dropped for missing duration)"
        )
    return entries, ledger


def disambiguate_slugs(entries, niche_root, channel):
    """Make slugs unique across the niche, not just within this channel's plan.

    A slug already claimed by a DIFFERENT channel's plan.jsonl gets a
    deterministic -2/-3 suffix, so two channels in one niche never share a
    videos/<slug>/ dir. Foreign plans are stable, so re-harvesting the same
    channel yields identical slugs (resume still works).
    """
    niche_root = Path(niche_root)
    foreign = set()
    harvest_dir = niche_root / "harvest"
    if harvest_dir.exists():
        for plan in harvest_dir.glob("*/plan.jsonl"):
            if plan.parent.name == channel:
                continue                      # our own plan — not a foreign claim
            for line in plan.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    foreign.add(json.loads(line)["slug"])
                except (ValueError, KeyError) as exc:
                    _log.warning("skipping corrupt row in foreign plan %s: %s", plan, exc)
    taken = set(foreign)
    out = []
    for e in entries:
        slug = e.slug
        if slug in taken:
            n = 2
            while f"{e.slug}-{n}" in taken:
                n += 1
            slug = f"{e.slug}-{n}"
        taken.add(slug)
        out.append(e if slug == e.slug else HarvestEntry(slug, e.topic, e.video_id, e.url, e.title))
    return out


def _plan_path(niche_root: Path, channel: str) -> Path:
    return Path(niche_root) / "harvest" / channel / "plan.jsonl"


def write_plan(entries: list[HarvestEntry], niche_root: Path, channel: str) -> Path:
    """Write entries as plan.jsonl, overwriting any existing plan.

    A re-harvest is meant to be idempotent, so the overwrite is intentional —
    but it can clobber a reviewed/hand-edited plan, so we log it.
    """
    path = _plan_path(niche_root, channel)
    if path.exists():
        _log.warning("overwriting existing plan %s", path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(asdict(e)) + "\n")
    return path


def read_plan(niche_root: Path, channel: str) -> list[HarvestEntry]:
    path = _plan_path(niche_root, channel)
    if not path.exists():
        raise MissingDataError(f"no harvest plan at {path}; run `pipeline harvest` first")
    out = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            out.append(HarvestEntry(**json.loads(line)))
        except (TypeError, ValueError) as exc:
            raise MissingDataError(f"malformed plan row {i} in {path}: {exc}") from exc
    return out
