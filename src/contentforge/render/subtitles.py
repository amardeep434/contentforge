"""Timed captions from the shots the video is already built from.

Every shot carries the sentence it narrates and the duration measured from its
own audio, so the subtitle track is not a second transcription that could drift
from the voice - it is the same timing the picture is cut to. One caption per
beat, spanning exactly that beat's audio.

Both SRT and WebVTT are emitted from one model. YouTube ingests either; WebVTT
is also what a `<track>` element wants, so a page embedding the mp4 gets
captions for free.

Long beats are wrapped to two on-screen lines so a caption never runs off the
frame - the split is on a word boundary near the middle, never mid-word.
"""

from dataclasses import dataclass

from contentforge.errors import MissingDataError

#: Above this many characters a caption is wrapped onto two lines. Sized to a
#: 1920px frame at the body face; wider than this and the line reaches the edge.
WRAP_OVER = 42


@dataclass(frozen=True)
class Cue:
    """One caption: when it starts, when it ends, what it says."""

    index: int
    start_s: float
    end_s: float
    text: str


def cues_from_shots(shots) -> list[Cue]:
    """One cue per shot, back to back, timed by measured audio."""
    if not shots:
        raise MissingDataError("no shots to caption")
    cues = []
    for index, shot in enumerate(shots, start=1):
        text = " ".join(shot.text.split())
        if not text:
            raise MissingDataError(f"shot {index} has no words to caption")
        cues.append(Cue(index=index, start_s=shot.start_s,
                        end_s=shot.end_s, text=text))
    return cues


def _wrap(text: str, limit: int = WRAP_OVER) -> str:
    """Two balanced lines when a caption is too long for one, else unchanged."""
    if len(text) <= limit:
        return text
    words = text.split()
    if len(words) < 2:
        return text
    target = len(text) // 2
    best, run = 0, 0
    for position, word in enumerate(words[:-1], start=1):
        run += len(word) + 1
        if abs(run - target) < abs(best - target) or best == 0:
            best, split_at = run, position
    return "\n".join([" ".join(words[:split_at]), " ".join(words[split_at:])])


def _clock(seconds: float, comma: bool) -> str:
    """`HH:MM:SS,mmm` for SRT or `HH:MM:SS.mmm` for WebVTT."""
    if seconds < 0:
        raise MissingDataError("a caption cannot start before the video does")
    milli = int(round(seconds * 1000))
    hours, milli = divmod(milli, 3_600_000)
    minutes, milli = divmod(milli, 60_000)
    secs, milli = divmod(milli, 1000)
    sep = "," if comma else "."
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{sep}{milli:03d}"


def to_srt(cues: list[Cue]) -> str:
    if not cues:
        raise MissingDataError("no cues to write")
    blocks = []
    for cue in cues:
        blocks.append(
            f"{cue.index}\n"
            f"{_clock(cue.start_s, True)} --> {_clock(cue.end_s, True)}\n"
            f"{_wrap(cue.text)}"
        )
    return "\n\n".join(blocks) + "\n"


def to_vtt(cues: list[Cue]) -> str:
    if not cues:
        raise MissingDataError("no cues to write")
    blocks = ["WEBVTT"]
    for cue in cues:
        blocks.append(
            f"{_clock(cue.start_s, False)} --> {_clock(cue.end_s, False)}\n"
            f"{_wrap(cue.text)}"
        )
    return "\n\n".join(blocks) + "\n"
