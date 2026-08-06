"""Shot planning: one image per narrated beat, timed by measured audio."""

from pathlib import Path

import pytest

from contentforge.errors import MissingDataError
from contentforge.visuals.compose import (
    MIN_SHOT_SECONDS,
    assert_continuous,
    merge_short_beats,
    plan_shots,
    split_beats,
    total_duration,
)
from contentforge.voice.backends import Clip


def clip(seconds, text="a beat", name="x.wav"):
    return Clip(path=Path(name), duration_s=seconds, text=text)


# --- beats ------------------------------------------------------------------

def test_a_script_splits_on_sentence_boundaries():
    beats = split_beats("He was born in 1839. He was rejected. Then everything changed!")
    assert len(beats) == 3
    assert beats[0].startswith("He was born")


def test_an_empty_script_raises():
    with pytest.raises(MissingDataError):
        split_beats("   ")


def test_very_short_sentences_merge_into_the_previous_beat():
    # "He refused." alone would be a flicker. Merging before synthesis keeps
    # audio and shots in step; merging after would orphan a clip.
    beats = merge_short_beats(
        ["Cezanne submitted to the Salon every year for two decades.", "He refused."]
    )
    assert len(beats) == 1
    assert beats[0].endswith("He refused.")


def test_a_short_opening_beat_is_kept_since_there_is_nothing_before_it():
    assert merge_short_beats(["He refused.", "A longer sentence follows here now."]) == [
        "He refused.",
        "A longer sentence follows here now.",
    ]


# --- shot planning ----------------------------------------------------------

def test_each_beat_becomes_one_shot_timed_by_its_own_audio():
    shots = plan_shots([clip(4.0), clip(6.5), clip(3.25)], ["a.jpg", "b.jpg", "c.jpg"])
    assert [s.duration_s for s in shots] == [4.0, 6.5, 3.25]
    assert [s.image_path for s in shots] == ["a.jpg", "b.jpg", "c.jpg"]


def test_shots_run_back_to_back():
    shots = plan_shots([clip(4.0), clip(6.0)], ["a.jpg", "b.jpg"])
    assert shots[0].start_s == 0.0
    assert shots[1].start_s == 4.0
    assert shots[1].end_s == 10.0
    assert total_duration(shots) == 10.0


def test_each_shot_keeps_its_own_audio_clip():
    shots = plan_shots([clip(3.0, name="beat_001.wav")], ["a.jpg"])
    assert shots[0].audio_path == "beat_001.wav"


def test_too_few_images_raises_rather_than_reusing_one():
    # Reusing an image is how a video ends up illustrated with material we do
    # not own (C-031).
    with pytest.raises(MissingDataError, match="do not own"):
        plan_shots([clip(3.0), clip(3.0)], ["only-one.jpg"])


def test_spare_images_are_allowed():
    shots = plan_shots([clip(3.0)], ["a.jpg", "b.jpg", "c.jpg"])
    assert len(shots) == 1


def test_a_beat_too_short_to_read_as_a_shot_raises():
    with pytest.raises(MissingDataError, match="flicker"):
        plan_shots([clip(5.0), clip(MIN_SHOT_SECONDS - 0.1)], ["a.jpg", "b.jpg"])


def test_no_clips_raises():
    with pytest.raises(MissingDataError):
        plan_shots([], ["a.jpg"])


# --- continuity -------------------------------------------------------------

def test_a_continuous_shot_list_passes():
    assert_continuous(plan_shots([clip(4.0), clip(5.0)], ["a.jpg", "b.jpg"]))


def test_a_gap_between_shots_raises():
    from contentforge.visuals.compose import Shot

    broken = [
        Shot("a.jpg", "a.wav", 0.0, 4.0, "one"),
        Shot("b.jpg", "b.wav", 9.0, 4.0, "two"),   # 5s hole
    ]
    with pytest.raises(MissingDataError, match="silence over a held frame"):
        assert_continuous(broken)


def test_an_empty_shot_list_raises():
    with pytest.raises(MissingDataError):
        assert_continuous([])
