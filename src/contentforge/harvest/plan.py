from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from contentforge.errors import MissingDataError

_NONWORD = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    return _NONWORD.sub("-", title.lower()).strip("-")


@dataclass(frozen=True)
class HarvestEntry:
    slug: str
    topic: str
    video_id: str
    url: str
    title: str


def build_plan(client, channel: str, ledger, limit: int):
    """Resolve a channel (a UC… id used directly, anything else treated as an
    @handle) and return (entries, ledger): one HarvestEntry per recent upload,
    topic = title, slug = slugify(title). The quota ledger is threaded through
    every API call and returned so the caller can persist it.

    NOTE: `get_videos` silently drops videos with no duration (live/upcoming) and
    `VideoRecord` carries no description, so `entries` may be shorter than `limit`
    and only the title is available (which is all harvest needs).
    """
    if channel.startswith("UC") and len(channel) == 24:
        channel_id = channel
    else:
        facts, ledger = client.channel_by_handle(channel.lstrip("@"), ledger)
        channel_id = facts.channel_id

    uploads, ledger = client.get_uploads_playlists([channel_id], ledger)
    playlist_id = uploads[channel_id]
    video_ids, ledger = client.get_playlist_video_ids(playlist_id, ledger, max_videos=limit)
    if not video_ids:
        raise MissingDataError(f"no videos found for channel {channel!r}")
    records, ledger = client.get_videos(video_ids, ledger)

    entries = [
        HarvestEntry(
            slug=slugify(r.title),
            topic=r.title,
            video_id=r.video_id,
            url=f"https://www.youtube.com/watch?v={r.video_id}",
            title=r.title,
        )
        for r in records
    ]
    return entries, ledger


def _plan_path(niche_root: Path, channel: str) -> Path:
    return Path(niche_root) / "harvest" / channel / "plan.jsonl"


def write_plan(entries: list[HarvestEntry], niche_root: Path, channel: str) -> Path:
    path = _plan_path(niche_root, channel)
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
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(HarvestEntry(**json.loads(line)))
    return out
