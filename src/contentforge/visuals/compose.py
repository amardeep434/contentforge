"""Cut the visuals against the narration.

One image per narration beat, held for exactly as long as that beat is spoken.
The timings come from `voice.speak`, which reports where every word lands, so
shot boundaries are measured rather than estimated — an estimate drifts, and
across twenty minutes it drifts visibly.

**A beat with no image is an error, never a repeat.** Filling a gap by holding
the previous image, or by dropping in stock, is what the failing copycat did
(C-031): found imagery pasted in, including a diagram it did not own. A shot
list that silently covers for missing assets produces a video that looks
finished and is not.

Niche-agnostic by design. It takes beats and images; it does not care whether
the images are paintings, diagrams or maps.
"""

import re
from dataclasses import dataclass

from contentforge.errors import MissingDataError

#: Sentence-ish. A beat is the unit a single image has to cover, and sentence
#: boundaries are where a narrator naturally pauses.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

#: Below this a shot is a flicker rather than a beat; adjacent short sentences
#: are merged into one shot instead.
MIN_SHOT_SECONDS = 2.5


@dataclass(frozen=True)
class Shot:
    image_path: str
    start_s: float
    duration_s: float
    text: str
    chapter: str = ""

    @property
    def end_s(self) -> float:
        return self.start_s + self.duration_s


def split_beats(script: str) -> list[str]:
    """Break narration into the units a single image must cover."""
    beats = [b.strip() for b in _SENTENCE_END.split(script or "") if b.strip()]
    if not beats:
        raise MissingDataError("script contains no narratable beats")
    return beats


def _normalise(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def beat_timings(beats: list[str], words) -> list[tuple[float, float]]:
    """Locate each beat in the narration timeline, by matching word sequences.

    Walks the timed word list in step with the beats. The narrator's words and
    the script's words differ in punctuation and casing but not in order, so
    consuming one word per script word keeps the two aligned without needing an
    exact match.
    """
    if not words:
        raise MissingDataError(
            "no word timings; shot boundaries would have to be guessed, and a "
            "guess drifts across a long video"
        )
    spans: list[tuple[float, float]] = []
    cursor = 0
    for beat in beats:
        count = len(_normalise(beat))
        if count == 0:
            continue
        start_index = min(cursor, len(words) - 1)
        end_index = min(cursor + count - 1, len(words) - 1)
        spans.append((words[start_index].start_s, words[end_index].end_s))
        cursor += count
    if not spans:
        raise MissingDataError("no beat could be located in the narration")
    return spans


def plan_shots(script: str, images: list[str], words, chapter: str = "") -> list[Shot]:
    """One shot per beat, timed against the narration.

    Raises when there are fewer images than beats rather than reusing one.
    """
    beats = split_beats(script)
    spans = beat_timings(beats, words)
    if len(images) < len(spans):
        raise MissingDataError(
            f"{len(spans)} narration beats but only {len(images)} images. A beat "
            "without its own image is an error, not a cue to hold the previous "
            "one - that is how a video ends up illustrated with someone else's "
            "material."
        )

    shots: list[Shot] = []
    for index, (start, end) in enumerate(spans):
        duration = max(end - start, 0.0)
        if shots and duration < MIN_SHOT_SECONDS:
            # Too short to register as its own shot: extend the previous one.
            previous = shots[-1]
            shots[-1] = Shot(
                image_path=previous.image_path,
                start_s=previous.start_s,
                duration_s=previous.duration_s + duration,
                text=f"{previous.text} {beats[index]}".strip(),
                chapter=previous.chapter,
            )
            continue
        shots.append(
            Shot(
                image_path=images[len(shots)],
                start_s=start,
                duration_s=duration,
                text=beats[index],
                chapter=chapter,
            )
        )
    return shots


def total_duration(shots: list[Shot]) -> float:
    return sum(shot.duration_s for shot in shots)


def assert_covers(shots: list[Shot], narration_duration: float, tolerance: float = 1.0):
    """Fail when the shot list does not span the narration.

    A gap is silence over a frozen frame; an overrun is audio that outlives the
    picture. Both look like a broken render rather than a stylistic choice.
    """
    if not shots:
        raise MissingDataError("no shots planned")
    covered = shots[-1].end_s
    if abs(covered - narration_duration) > tolerance:
        raise MissingDataError(
            f"shots cover {covered:.1f}s but the narration runs "
            f"{narration_duration:.1f}s - the difference would render as silence "
            "over a held frame, or audio past the last image"
        )
