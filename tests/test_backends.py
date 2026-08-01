"""Speech backends and per-beat synthesis."""

import base64
import json
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from contentforge.errors import MissingDataError
from contentforge.voice.backends import (
    PCM_RATE,
    Clip,
    gemini_runner,
    measure_duration,
    synthesise_beats,
    total_seconds,
    wrap_pcm_as_wav,
)


# --- PCM wrapping -----------------------------------------------------------

def test_raw_pcm_becomes_a_playable_wav():
    # Gemini returns headerless PCM; without a RIFF header nothing will play it
    # and ffmpeg reports a corrupt file.
    wav = wrap_pcm_as_wav(b"\x00\x01" * 100)
    assert wav[:4] == b"RIFF"
    assert wav[8:12] == b"WAVE"
    assert b"data" in wav[:64]


def test_the_header_declares_the_right_sample_rate():
    wav = wrap_pcm_as_wav(b"\x00\x01" * 10)
    rate = struct.unpack("<I", wav[24:28])[0]
    assert rate == PCM_RATE


def test_the_payload_survives_intact():
    pcm = bytes(range(256)) * 4
    assert wrap_pcm_as_wav(pcm).endswith(pcm)


# --- Gemini -----------------------------------------------------------------

def fake_response(pcm=b"\x00\x01" * 50):
    body = {
        "candidates": [
            {"content": {"parts": [
                {"inlineData": {"data": base64.b64encode(pcm).decode()}}
            ]}}
        ]
    }

    class _Ctx:
        def __enter__(self):
            return SimpleNamespace(read=lambda: json.dumps(body).encode())

        def __exit__(self, *a):
            return False

    return lambda request, timeout=None: _Ctx()


def test_a_missing_key_raises_with_where_to_get_one():
    with pytest.raises(MissingDataError, match="aistudio.google.com"):
        gemini_runner("hello", api_key="")


def test_audio_comes_back_as_wav():
    audio = gemini_runner("hello", api_key="k", opener=fake_response())
    assert audio[:4] == b"RIFF"


def test_the_key_travels_in_a_header_not_the_body():
    seen = {}

    def opener(request, timeout=None):
        seen["headers"] = dict(request.headers)
        seen["body"] = request.data.decode()
        return fake_response()(request)

    gemini_runner("hello", api_key="secret", opener=opener)
    assert any(v == "secret" for v in seen["headers"].values())
    assert "secret" not in seen["body"]


def test_the_chosen_voice_reaches_the_request():
    seen = {}

    def opener(request, timeout=None):
        seen["body"] = json.loads(request.data.decode())
        return fake_response()(request)

    gemini_runner("hi", voice="Kore", api_key="k", opener=opener)
    speech = seen["body"]["generationConfig"]["speechConfig"]
    assert speech["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Kore"


def test_a_refusal_with_no_audio_raises():
    class _Ctx:
        def __enter__(self):
            return SimpleNamespace(read=lambda: json.dumps({"candidates": []}).encode())

        def __exit__(self, *a):
            return False

    with pytest.raises(MissingDataError, match="no audio payload"):
        gemini_runner("x", api_key="k", opener=lambda r, timeout=None: _Ctx())


def test_the_api_key_never_appears_in_an_error():
    # Gemini echoes the request in its errors; passing that through would leak
    # the key into logs.
    def boom(request, timeout=None):
        raise OSError("HTTP 400: bad key SECRETKEY123 in x-goog-api-key")

    with pytest.raises(MissingDataError) as caught:
        gemini_runner("x", api_key="SECRETKEY123", opener=boom)
    assert "SECRETKEY123" not in str(caught.value)


# --- duration ---------------------------------------------------------------

def test_duration_is_read_from_the_file():
    result = SimpleNamespace(stdout="12.94\n", stderr="")
    assert measure_duration(Path("/x.wav"), runner=lambda *a, **k: result) == 12.94


def test_an_unreadable_duration_raises():
    result = SimpleNamespace(stdout="not a number", stderr="")
    with pytest.raises(MissingDataError):
        measure_duration(Path("/x.wav"), runner=lambda *a, **k: result)


def test_a_zero_duration_raises():
    result = SimpleNamespace(stdout="0.0", stderr="")
    with pytest.raises(MissingDataError):
        measure_duration(Path("/x.wav"), runner=lambda *a, **k: result)


# --- per-beat synthesis -----------------------------------------------------

def speaker(tmp_path, size=100):
    def _speak(text, path):
        path.write_bytes(b"\x00" * size)
        return path

    return _speak


def test_one_clip_per_beat_each_timed_individually(tmp_path):
    clips = synthesise_beats(
        ["First beat.", "Second beat.", "Third."],
        tmp_path,
        speak=speaker(tmp_path),
        timer=lambda p: 4.0,
    )
    assert [c.text for c in clips] == ["First beat.", "Second beat.", "Third."]
    assert total_seconds(clips) == 12.0


def test_durations_come_from_the_audio_not_an_estimate(tmp_path):
    measured = iter([3.0, 7.5])
    clips = synthesise_beats(
        ["a", "b"], tmp_path, speak=speaker(tmp_path), timer=lambda p: next(measured)
    )
    assert [c.duration_s for c in clips] == [3.0, 7.5]


def test_a_silent_beat_raises_rather_than_shortening_the_video(tmp_path):
    def broken(text, path):
        path.write_bytes(b"")
        return path

    with pytest.raises(MissingDataError, match="desynchronise"):
        synthesise_beats(["a"], tmp_path, speak=broken, timer=lambda p: 1.0)


def test_no_beats_raises(tmp_path):
    with pytest.raises(MissingDataError):
        synthesise_beats([], tmp_path, speak=speaker(tmp_path), timer=lambda p: 1.0)


def test_clips_are_written_where_asked(tmp_path):
    clips = synthesise_beats(
        ["a", "b"], tmp_path / "voice", speak=speaker(tmp_path), timer=lambda p: 1.0
    )
    assert all(c.path.exists() for c in clips)
    assert clips[0].path.name == "beat_001.wav"


# --- pacing and rate limits -------------------------------------------------

def test_the_pacing_directive_is_prepended_to_the_narration():
    # Gemini has no rate parameter. Measured on a 41-word passage: no
    # instruction gives 180 wpm, this directive gives 148, against the
    # reference channel's 142.
    from contentforge.voice.backends import NARRATION_STYLE

    seen = {}

    def opener(request, timeout=None):
        seen["body"] = json.loads(request.data.decode())
        return fake_response()(request)

    gemini_runner("A fan does not cool a room.", api_key="k", opener=opener)
    spoken = seen["body"]["contents"][0]["parts"][0]["text"]
    assert spoken.startswith(NARRATION_STYLE)
    assert spoken.endswith("A fan does not cool a room.")


def test_pacing_can_be_turned_off():
    seen = {}

    def opener(request, timeout=None):
        seen["body"] = json.loads(request.data.decode())
        return fake_response()(request)

    gemini_runner("Bare text.", api_key="k", style="", opener=opener)
    assert seen["body"]["contents"][0]["parts"][0]["text"] == "Bare text."


def _http_error(status):
    import urllib.error

    return urllib.error.HTTPError("u", status, "msg", {}, None)


def test_a_rate_limit_is_retried_rather_than_failing_the_render():
    # A 200-beat video exhausts the free tier's per-minute allowance many times
    # over. Treating that as an error would make the backend unusable.
    attempts = []

    def opener(request, timeout=None):
        attempts.append(1)
        if len(attempts) < 3:
            raise _http_error(429)
        return fake_response()(request)

    audio = gemini_runner("x", api_key="k", opener=opener, sleeper=lambda _: None)
    assert audio[:4] == b"RIFF"
    assert len(attempts) == 3


def test_a_bad_request_is_not_retried():
    attempts = []

    def opener(request, timeout=None):
        attempts.append(1)
        raise _http_error(400)

    with pytest.raises(MissingDataError, match="HTTP 400"):
        gemini_runner("x", api_key="k", opener=opener, sleeper=lambda _: None)
    assert len(attempts) == 1


def test_persistent_rate_limiting_eventually_gives_up_and_says_so():
    def opener(request, timeout=None):
        raise _http_error(429)

    with pytest.raises(MissingDataError, match="exhausting retries"):
        gemini_runner("x", api_key="k", opener=opener, sleeper=lambda _: None)


def test_an_http_error_never_carries_the_key():
    def opener(request, timeout=None):
        raise _http_error(403)

    with pytest.raises(MissingDataError) as caught:
        gemini_runner("x", api_key="SECRETKEY123", opener=opener,
                      sleeper=lambda _: None)
    assert "SECRETKEY123" not in str(caught.value)
