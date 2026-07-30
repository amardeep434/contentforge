"""Narration.

Two jobs: never speak a citation marker, and report where each word lands so the
visuals can be cut against the narration rather than guessed at.
"""

from datetime import timedelta
from pathlib import Path

import pytest

from contentforge.errors import MissingDataError
from contentforge.voice.speak import (
    TICKS_PER_SECOND,
    Narration,
    strip_citations,
    synthesise,
    to_seconds,
)


# --- citation stripping -----------------------------------------------------

def test_citation_markers_are_removed_before_narration():
    assert strip_citations("Air moves fast [1] and cooks food [2].") == (
        "Air moves fast and cooks food."
    )


def test_multi_digit_markers_are_removed():
    assert strip_citations("A claim [22] and another [107].") == (
        "A claim and another."
    )


def test_spacing_is_left_clean():
    assert "  " not in strip_citations("A [1] B [22] C.")


def test_punctuation_is_not_orphaned():
    # "food [2]." must not become "food ." — the narrator pauses oddly on it.
    assert strip_citations("It cooks food [2].") == "It cooks food."


def test_text_without_markers_is_unchanged():
    assert strip_citations("Nothing to strip here.") == "Nothing to strip here."


def test_square_brackets_that_are_not_citations_survive():
    # A year or an editorial insertion is not a citation marker.
    assert strip_citations("He wrote [sic] in 1890.") == "He wrote [sic] in 1890."


def test_a_script_that_is_only_citations_raises():
    # Synthesising silence would produce a video with no narration at all.
    with pytest.raises(MissingDataError):
        strip_citations("[1] [2] [3]")


def test_empty_input_raises():
    with pytest.raises(MissingDataError):
        strip_citations("   ")


# --- timings ----------------------------------------------------------------

def test_ticks_convert_to_seconds():
    # edge-tts reports offsets in 100-nanosecond ticks, as SSML does.
    assert to_seconds(TICKS_PER_SECOND) == 1.0
    assert to_seconds(5_000_000) == 0.5


def test_word_timings_are_exposed_in_seconds():
    narration = synthesise(
        "Hello world",
        Path("/tmp/x.mp3"),
        runner=fake_runner(
            audio=b"ID3audio",
            boundaries=[
                {"type": "WordBoundary", "offset": 0, "duration": 5_000_000, "text": "Hello"},
                {"type": "WordBoundary", "offset": 5_000_000, "duration": 5_000_000, "text": "world"},
            ],
        ),
        writer=lambda path, data: path,
    )
    assert [w.word for w in narration.words] == ["Hello", "world"]
    assert narration.words[1].start_s == 0.5


def test_duration_is_the_end_of_the_last_word():
    narration = synthesise(
        "Hello world",
        Path("/tmp/x.mp3"),
        runner=fake_runner(
            audio=b"ID3audio",
            boundaries=[
                {"type": "WordBoundary", "offset": 0, "duration": 5_000_000, "text": "Hello"},
                {"type": "WordBoundary", "offset": 5_000_000, "duration": 5_000_000, "text": "world"},
            ],
        ),
        writer=lambda path, data: path,
    )
    assert narration.duration_s == 1.0


def test_non_word_events_are_ignored():
    narration = synthesise(
        "Hi",
        Path("/tmp/x.mp3"),
        runner=fake_runner(
            audio=b"ID3audio",
            boundaries=[
                {"type": "audio", "data": b"..."},
                {"type": "WordBoundary", "offset": 0, "duration": 1_000_000, "text": "Hi"},
            ],
        ),
        writer=lambda path, data: path,
    )
    assert len(narration.words) == 1


# --- synthesis --------------------------------------------------------------

def fake_runner(audio=b"ID3audio", boundaries=()):
    def _runner(text, voice):
        return audio, list(boundaries)

    return _runner


def test_the_narrator_never_receives_a_citation_marker():
    seen = {}

    def _runner(text, voice):
        seen["text"] = text
        return b"ID3audio", [{"type": "WordBoundary", "offset": 0, "duration": 10, "text": "x"}]

    synthesise(
        "Cezanne was rejected [1].",
        Path("/tmp/x.mp3"),
        runner=_runner,
        writer=lambda path, data: path,
    )
    assert "[1]" not in seen["text"]


def test_the_chosen_voice_is_passed_through():
    seen = {}

    def _runner(text, voice):
        seen["voice"] = voice
        return b"ID3audio", [{"type": "WordBoundary", "offset": 0, "duration": 10, "text": "x"}]

    synthesise(
        "Hello",
        Path("/tmp/x.mp3"),
        voice="en-GB-RyanNeural",
        runner=_runner,
        writer=lambda path, data: path,
    )
    assert seen["voice"] == "en-GB-RyanNeural"


def test_empty_audio_raises_rather_than_writing_a_silent_file():
    # A zero-byte mp3 renders as a video with no sound, which looks like success.
    with pytest.raises(MissingDataError):
        synthesise(
            "Hello",
            Path("/tmp/x.mp3"),
            runner=fake_runner(audio=b""),
            writer=lambda path, data: path,
        )


def test_no_word_boundaries_raises():
    # Without timings the visuals cannot be cut against the narration, and
    # guessing durations is how a video drifts out of sync.
    with pytest.raises(MissingDataError):
        synthesise(
            "Hello",
            Path("/tmp/x.mp3"),
            runner=fake_runner(audio=b"ID3audio", boundaries=[]),
            writer=lambda path, data: path,
        )


def test_a_runner_failure_becomes_missing_data():
    def boom(text, voice):
        raise OSError("websocket closed")

    with pytest.raises(MissingDataError):
        synthesise("Hello", Path("/tmp/x.mp3"), runner=boom, writer=lambda p, d: p)


def test_audio_is_written_and_the_path_returned(tmp_path):
    out = tmp_path / "narration.mp3"
    narration = synthesise(
        "Hello",
        out,
        runner=fake_runner(
            audio=b"ID3audio",
            boundaries=[{"type": "WordBoundary", "offset": 0, "duration": 10_000_000, "text": "Hello"}],
        ),
    )
    assert isinstance(narration, Narration)
    assert narration.path == out
    assert out.read_bytes() == b"ID3audio"


def test_narration_reports_a_readable_duration():
    narration = Narration(path=Path("/x"), duration_s=95.5, words=())
    assert narration.length == timedelta(seconds=95.5)
