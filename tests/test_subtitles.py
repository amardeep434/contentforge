"""Timed captions, from the same shot timing the video is cut to."""

import pytest

from contentforge.errors import MissingDataError
from contentforge.render.subtitles import (
    Cue,
    cues_from_shots,
    to_srt,
    to_vtt,
)
from contentforge.visuals.compose import Shot


def shot(start, dur, text):
    return Shot("i.png", "a.wav", start, dur, text)


def test_one_cue_per_shot_timed_by_its_audio():
    cues = cues_from_shots([shot(0.0, 4.0, "One."), shot(4.0, 6.5, "Two.")])
    assert [(c.start_s, c.end_s) for c in cues] == [(0.0, 4.0), (4.0, 10.5)]
    assert [c.text for c in cues] == ["One.", "Two."]


def test_no_shots_raises():
    with pytest.raises(MissingDataError, match="no shots"):
        cues_from_shots([])


def test_a_shot_with_no_words_raises():
    with pytest.raises(MissingDataError, match="no words"):
        cues_from_shots([shot(0.0, 4.0, "   ")])


# --- SRT --------------------------------------------------------------------

def test_srt_timestamps_use_a_comma_and_milliseconds():
    srt = to_srt([Cue(1, 0.0, 4.25, "Hello.")])
    assert "00:00:00,000 --> 00:00:04,250" in srt
    assert srt.startswith("1\n")


def test_srt_clock_rolls_over_hours_and_minutes():
    srt = to_srt([Cue(1, 3661.5, 3662.0, "x")])
    assert "01:01:01,500 --> 01:01:02,000" in srt


# --- VTT --------------------------------------------------------------------

def test_vtt_starts_with_the_header_and_uses_a_dot():
    vtt = to_vtt([Cue(1, 0.0, 4.25, "Hello.")])
    assert vtt.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:04.250" in vtt


# --- wrapping ---------------------------------------------------------------

def test_a_long_caption_is_wrapped_onto_two_lines():
    long = "This is a fairly long single caption that will not fit on one line."
    body = to_srt([Cue(1, 0.0, 3.0, long)])
    caption = body.split("\n", 2)[2]
    assert "\n" in caption.strip()
    # never split mid-word
    assert "  " not in caption


def test_a_short_caption_is_left_on_one_line():
    body = to_srt([Cue(1, 0.0, 3.0, "Short one.")])
    assert body.strip().endswith("Short one.")


def test_a_negative_start_is_rejected():
    with pytest.raises(MissingDataError, match="before the video"):
        to_srt([Cue(1, -0.1, 3.0, "x")])
