"""Cut the visuals against the narration.

One image per narration beat, held for exactly as long as that beat is spoken.

Durations come from `voice.backends.synthesise_beats`, which narrates each beat
separately and measures the resulting audio. That is deliberate: it makes shot
boundaries exact by construction rather than inferred from a word-timing stream,
and it works with any speech backend — edge-tts reports word boundaries, Gemini
reports none, and this module does not care.

**A beat with no image is an error, never a repeat.** Filling a gap by holding
the previous image, or dropping in stock, is what the failing copycat did
(C-031): found imagery pasted in, including a diagram it did not own. A shot
list that silently covers for missing assets produces a video that looks
finished and is not.

Niche-agnostic: it takes beats and images and does not care whether the images
are paintings, diagrams or maps.
"""

import re
from dataclasses import dataclass

from contentforge.errors import MissingDataError

#: A beat is the unit one image has to cover. Sentence boundaries are where a
#: narrator naturally pauses, so they are where a cut is least noticeable.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

#: Below this, a shot reads as a flicker rather than a beat.
MIN_SHOT_SECONDS = 2.0


@dataclass(frozen=True)
class Shot:
    image_path: str
    audio_path: str
    start_s: float
    duration_s: float
    text: str

    @property
    def end_s(self) -> float:
        return self.start_s + self.duration_s


def split_beats(script: str) -> list[str]:
    """Break narration into the units a single image must cover."""
    beats = [b.strip() for b in _SENTENCE_END.split(script or "") if b.strip()]
    if not beats:
        raise MissingDataError("script contains no narratable beats")
    return beats


def merge_short_beats(beats: list[str], min_words: int = 6) -> list[str]:
    """Fold very short sentences into the one before.

    "He refused." on its own image is a flicker. Merging before synthesis keeps
    the audio and the shot list in step - merging afterwards would leave an
    orphan clip.
    """
    merged: list[str] = []
    for beat in beats:
        if merged and len(beat.split()) < min_words:
            merged[-1] = f"{merged[-1]} {beat}"
        else:
            merged.append(beat)
    return merged


def plan_shots(clips, images: list[str]) -> list[Shot]:
    """One shot per narrated clip, timed by that clip's measured duration."""
    if not clips:
        raise MissingDataError("no narration clips to build shots from")
    if len(images) < len(clips):
        raise MissingDataError(
            f"{len(clips)} narration beats but only {len(images)} images. A beat "
            "without its own image is an error, not a cue to hold the previous "
            "one - that is how a video ends up illustrated with material we do "
            "not own."
        )

    shots: list[Shot] = []
    cursor = 0.0
    for index, clip in enumerate(clips):
        if clip.duration_s < MIN_SHOT_SECONDS:
            raise MissingDataError(
                f"beat {index + 1} narrates in {clip.duration_s:.1f}s, under the "
                f"{MIN_SHOT_SECONDS}s minimum - it would read as a flicker. Merge "
                "it into a neighbouring beat before synthesis."
            )
        shots.append(
            Shot(
                image_path=images[index],
                audio_path=str(clip.path),
                start_s=cursor,
                duration_s=clip.duration_s,
                text=clip.text,
            )
        )
        cursor += clip.duration_s
    return shots


def total_duration(shots: list[Shot]) -> float:
    return sum(shot.duration_s for shot in shots)


def assert_continuous(shots: list[Shot], tolerance: float = 0.01) -> None:
    """Every shot must begin where the previous one ended.

    A gap renders as silence over a frozen frame and an overlap as a dropped
    image; both look like a broken render rather than a choice.
    """
    if not shots:
        raise MissingDataError("no shots planned")
    for previous, current in zip(shots, shots[1:]):
        if abs(current.start_s - previous.end_s) > tolerance:
            raise MissingDataError(
                f"shot at {current.start_s:.2f}s does not follow the previous one "
                f"ending at {previous.end_s:.2f}s - the difference would render "
                "as silence over a held frame"
            )
