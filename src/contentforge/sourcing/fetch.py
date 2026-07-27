"""Retrieve and store primary sources.

Stored in full so a script can be re-checked later against exactly what was
available when it was written. A source that cannot be fetched is an error,
never an empty entry — a script grounded in nothing is the failure mode this
whole design exists to prevent.
"""

import html
import json
import re
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from contentforge.errors import MissingDataError

_TAGS = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.S | re.I)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)


def http_get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "contentforge/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def _strip(markup: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", _TAGS.sub(" ", markup))).strip()


@dataclass(frozen=True)
class Source:
    url: str
    title: str
    text: str
    retrieved_at: datetime


def fetch_source(url: str, transport: Callable[[str], str] = http_get, now=None) -> Source:
    now = now or datetime.now(timezone.utc)
    markup = transport(url)
    text = _strip(markup)
    if not text:
        raise MissingDataError(f"{url} yielded no text")
    match = _TITLE.search(markup)
    return Source(url=url, title=_strip(match.group(1)) if match else url,
                  text=text, retrieved_at=now)


def save_sources(sources: list[Source], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "sources.json"
    path.write_text(json.dumps(
        [{"url": s.url, "title": s.title, "text": s.text,
          "retrieved_at": s.retrieved_at.isoformat()} for s in sources], indent=2))
    return path


def load_sources(directory: Path) -> list[Source]:
    path = directory / "sources.json"
    if not path.exists():
        raise MissingDataError(f"no sources at {path}")
    records = json.loads(path.read_text())
    if not records:
        raise MissingDataError(f"{path} is empty")
    return [Source(r["url"], r["title"], r["text"],
                   datetime.fromisoformat(r["retrieved_at"])) for r in records]
