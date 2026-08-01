"""Compose shots and narration into an mp4.

Split so the ffmpeg invocation is testable without running ffmpeg:
`build_commands` is pure and asserted against, `render` shells out through an
injected runner. Every ffmpeg bug this pipeline has is then a unit test rather
than a twenty-minute render that has to be watched to be checked.

Two files are written per render — a concat list for the audio and a filter
script for the video — because a twenty-minute video has ~150 shots and the
argument list would otherwise exceed what a shell will accept.

A non-zero exit deletes the part-written output. An mp4 that exists but is
truncated is worse than no mp4: it looks like the render worked.
"""

import shlex
import subprocess
from pathlib import Path
from typing import Callable

from contentforge.errors import MissingDataError

WIDTH, HEIGHT = 1920, 1080
FPS = 30

#: Slow push on each still, so a held image is not a frozen frame. The exemplar
#: does exactly this and nothing more; C-011 says do not spend beyond it.
ZOOM_PER_FRAME = 0.0004
MAX_ZOOM = 1.10


def _escape(path: Path | str) -> str:
    return str(path).replace("'", r"'\''")


def build_concat_file(shots) -> str:
    """ffconcat list for the narration clips, in order."""
    if not shots:
        raise MissingDataError("no shots to render")
    lines = ["ffconcat version 1.0"]
    for shot in shots:
        lines.append(f"file '{_escape(shot.audio_path)}'")
    return "\n".join(lines) + "\n"


def build_filter_script(shots) -> str:
    """One zoompan segment per shot, concatenated.

    Durations are per-shot rather than a global frame count: a rounding error
    repeated 150 times drifts the picture off the narration by seconds.
    """
    if not shots:
        raise MissingDataError("no shots to render")
    parts = []
    for index, shot in enumerate(shots):
        frames = max(int(round(shot.duration_s * FPS)), 1)
        parts.append(
            f"[{index}:v]scale={WIDTH * 2}:-1,"
            f"zoompan=z='min(zoom+{ZOOM_PER_FRAME},{MAX_ZOOM})':"
            f"d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS},"
            f"setsar=1[v{index}]"
        )
    chain = "".join(f"[v{i}]" for i in range(len(shots)))
    parts.append(f"{chain}concat=n={len(shots)}:v=1:a=0[outv]")
    return ";".join(parts)


def build_commands(shots, out_path: Path, work_dir: Path) -> tuple[list[str], dict]:
    """The ffmpeg argv plus the sidecar files it needs written first."""
    if not shots:
        raise MissingDataError("no shots to render")
    concat_path = work_dir / "audio.ffconcat"
    filter_path = work_dir / "filter.txt"

    argv = ["ffmpeg", "-y"]
    for shot in shots:
        argv += ["-loop", "1", "-i", str(shot.image_path)]
    argv += ["-f", "concat", "-safe", "0", "-i", str(concat_path)]
    argv += [
        "-filter_complex_script", str(filter_path),
        "-map", "[outv]",
        "-map", f"{len(shots)}:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        # Without this the video runs to the longest input - the looped stills
        # never end, so the render would never terminate.
        "-shortest",
        str(out_path),
    ]
    sidecars = {
        concat_path: build_concat_file(shots),
        filter_path: build_filter_script(shots),
    }
    return argv, sidecars


def render(
    shots,
    out_path: Path,
    work_dir: Path,
    runner: Callable = subprocess.run,
    writer: Callable[[Path, str], None] | None = None,
) -> Path:
    """Render, or raise with ffmpeg's own diagnosis attached."""
    work_dir.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    argv, sidecars = build_commands(shots, out_path, work_dir)

    write = writer or (lambda path, text: path.write_text(text))
    for path, text in sidecars.items():
        write(path, text)

    finished = runner(argv, capture_output=True, text=True, timeout=7200)
    if getattr(finished, "returncode", 1) != 0:
        # A truncated mp4 looks like success to everything downstream.
        if out_path.exists():
            out_path.unlink()
        tail = "\n".join((finished.stderr or "").strip().splitlines()[-12:])
        raise MissingDataError(f"ffmpeg failed:\n{tail}")
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise MissingDataError(
            f"ffmpeg reported success but {out_path} is missing or empty"
        )
    return out_path


def preview_command(shots, out_path: Path, work_dir: Path) -> str:
    """The exact command, for pasting into a shell when a render misbehaves."""
    argv, _ = build_commands(shots, out_path, work_dir)
    return " ".join(shlex.quote(a) for a in argv)
