"""Fetch a video's captions with yt-dlp and reduce them to plain text.

The transcript is used only as source material the script rewrites - never
relayed. yt-dlp is a subprocess (injected as `runner` for tests)."""
from __future__ import annotations

import glob
import os
import re
import subprocess
import tempfile
from pathlib import Path

from contentforge.errors import MissingDataError

_TS = re.compile(r"-->")
_TAG = re.compile(r"<[^>]+>")


def vtt_to_text(vtt: str) -> str:
    lines = []
    for raw in vtt.splitlines():
        line = raw.strip()
        if not line or line == "WEBVTT" or _TS.search(line) or line.isdigit():
            continue
        if line.startswith(("Kind:", "Language:", "NOTE")):
            continue
        line = _TAG.sub("", line)
        if line and (not lines or lines[-1] != line):   # drop consecutive dupes (auto-caption rolls)
            lines.append(line)
    return " ".join(lines).strip()


def fetch_transcript(video: str, runner=subprocess.run) -> str:
    """Download English auto-captions with yt-dlp into a temp dir and return the
    plain text. `video` may be a full URL or a bare id. `runner` is injected so
    tests never shell out. Raises MissingDataError if the video has no captions.
    """
    vid = video.rsplit("=", 1)[-1].rsplit("/", 1)[-1]        # bare id for the URL + filename
    url = video if video.startswith("http") else f"https://www.youtube.com/watch?v={vid}"
    with tempfile.TemporaryDirectory() as tmp:
        out_template = os.path.join(tmp, "%(id)s.%(ext)s")   # yt-dlp -> <tmp>/<id>.en.vtt
        runner(
            ["yt-dlp", "--write-auto-subs", "--sub-langs", "en", "--skip-download",
             "--sub-format", "vtt", "-o", out_template, url],
            capture_output=True, text=True,
        )
        vtts = glob.glob(os.path.join(tmp, "*.vtt"))
        if not vtts:
            raise MissingDataError(f"no captions for {vid}")
        text = vtt_to_text(Path(vtts[0]).read_text(encoding="utf-8"))
    if not text:
        raise MissingDataError(f"no captions for {vid}")
    return text
