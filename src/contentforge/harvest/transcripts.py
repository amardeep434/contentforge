"""Fetch a video's captions with yt-dlp and reduce them to plain text.

The transcript is used only as source material the script rewrites - never
relayed. yt-dlp is a subprocess (injected as `runner` for tests)."""
from __future__ import annotations

import glob
import html
import os
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from contentforge.errors import MissingDataError

_TS = re.compile(r"-->")
_TAG = re.compile(r"<[^>]+>")


def vtt_to_text(vtt: str) -> str:
    lines = []
    for raw in vtt.splitlines():
        line = raw.strip()
        if not line or line.startswith("WEBVTT") or _TS.search(line) or line.isdigit():
            continue
        if line.startswith(("Kind:", "Language:", "NOTE")):
            continue
        line = html.unescape(_TAG.sub("", line))
        if line and (not lines or lines[-1] != line):   # drop consecutive dupes (auto-caption rolls)
            lines.append(line)
    return " ".join(lines).strip()


def _video_id(video: str) -> str:
    """Extract the bare video id from a full URL or pass a bare id through.

    Handles `watch?v=<id>&list=...`, `youtu.be/<id>?t=...`, and bare ids -
    query/fragment params (list=, t=, ...) never leak into the id.
    """
    if not video.startswith("http"):
        return video
    parsed = urlparse(video)
    qs = parse_qs(parsed.query)
    if "v" in qs:
        return qs["v"][0]
    return parsed.path.rsplit("/", 1)[-1]


def fetch_transcript(video: str, runner=subprocess.run) -> str:
    """Download English auto-captions with yt-dlp into a temp dir and return the
    plain text. `video` may be a full URL or a bare id. `runner` is injected so
    tests never shell out. Raises MissingDataError if yt-dlp fails or the video
    has no captions.
    """
    vid = _video_id(video)
    url = video if video.startswith("http") else f"https://www.youtube.com/watch?v={vid}"
    with tempfile.TemporaryDirectory() as tmp:
        out_template = os.path.join(tmp, "%(id)s.%(ext)s")   # yt-dlp -> <tmp>/<id>.en.vtt
        result = runner(
            ["yt-dlp", "--write-auto-subs", "--sub-langs", "en", "--skip-download",
             "--sub-format", "vtt", "--no-playlist", "-o", out_template, url],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise MissingDataError(f"yt-dlp failed for {vid}: {result.stderr}")
        vtts = glob.glob(os.path.join(tmp, "*.vtt"))
        if not vtts:
            raise MissingDataError(f"no captions for {vid}")
        text = vtt_to_text(Path(vtts[0]).read_text(encoding="utf-8"))
    if not text:
        raise MissingDataError(f"no captions for {vid}")
    return text
