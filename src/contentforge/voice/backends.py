"""Speech backends, and per-beat synthesis.

Two problems solved together.

**Voice quality.** Every edge-tts voice tried was judged obviously synthetic
against a human reference (C-049). Gemini's TTS models run on the same free key
as its text models and are a materially different engine, so they are worth a
listen before concluding the gap is unbridgeable.

**Timings.** edge-tts reports word boundaries; Gemini reports nothing. Rather
than making the pipeline depend on a feature only one backend has, narration is
synthesised **one clip per beat** and each clip's duration is measured from the
audio itself. Shot boundaries are then exact by construction, and the backend
becomes a one-line swap — which is the whole reason `synthesise` takes an
injected runner.

Measuring beats individually also removes the fuzzy word-matching that aligning
a script against a word-timing stream requires, and which drifts when the
narrator's words and the script's words disagree.
"""

import base64
import json
import os
import struct
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from contentforge.errors import MissingDataError

GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-preview-tts"
#: Chosen by the operator from six candidates reading the same passage at the
#: same pace, so the comparison was timbre and nothing else.
DEFAULT_GEMINI_VOICE = "Iapetus"

#: Gemini returns raw little-endian signed 16-bit PCM at 24 kHz, mono, with no
#: container. ffmpeg and every player need a WAV header wrapped around it.
PCM_RATE = 24_000
PCM_CHANNELS = 1
PCM_BITS = 16


@dataclass(frozen=True)
class Clip:
    path: Path
    duration_s: float
    text: str


def wrap_pcm_as_wav(pcm: bytes) -> bytes:
    """Add a RIFF header to raw PCM so the bytes are a playable file."""
    byte_rate = PCM_RATE * PCM_CHANNELS * PCM_BITS // 8
    block_align = PCM_CHANNELS * PCM_BITS // 8
    header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
    header += struct.pack(
        "<IHHIIHH", 16, 1, PCM_CHANNELS, PCM_RATE, byte_rate, block_align, PCM_BITS
    )
    header += b"data" + struct.pack("<I", len(pcm))
    return header + pcm


#: Gemini TTS has no rate parameter, so pace is set by instruction. Measured on
#: a 41-word passage, reference channel at 142 wpm:
#:
#:     no instruction                      180 wpm
#:     "read slowly and deliberately"      122 wpm
#:     the directive below                 148 wpm
#:
#: Within 5% of the exemplar, which is the tolerance C-047 established the pace
#: can be matched to. The wording is calibration, not decoration - editing it
#: changes the narration speed of every video.
NARRATION_STYLE = (
    "Narrate this like a documentary explainer, unhurried but not laboured:"
)

#: The free tier's per-minute limit is reached quickly when a video is 150-250
#: beats, so a rejected request is expected traffic rather than an error.
MAX_ATTEMPTS = 5
BACKOFF_SECONDS = 12


def gemini_runner(
    text: str,
    voice: str = DEFAULT_GEMINI_VOICE,
    model: str = DEFAULT_GEMINI_MODEL,
    api_key: str | None = None,
    opener: Callable | None = None,
    style: str = NARRATION_STYLE,
    sleeper: Callable[[float], None] | None = None,
) -> bytes:
    """One utterance from Gemini TTS, returned as WAV bytes.

    The key comes from the environment and is never logged: Gemini rejects a bad
    key with a message that echoes the request, so error text is not passed
    through. The HTTP status is, because "429" and "400" call for opposite
    responses and hiding both made a rate limit look like a broken request.
    """
    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise MissingDataError(
            "GEMINI_API_KEY is not set. Gemini TTS runs on the same free key as "
            "its text models; get one at aistudio.google.com/apikey"
        )
    spoken = f"{style}\n\n{text}" if style else text
    payload = {
        "contents": [{"parts": [{"text": spoken}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}
            },
        },
    }
    request = urllib.request.Request(
        GEMINI_ENDPOINT.format(model=model),
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    open_url = opener or urllib.request.urlopen
    pause = sleeper if sleeper is not None else time.sleep
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with open_url(request, timeout=180) as response:
                body = json.loads(response.read().decode())
            break
        except MissingDataError:
            raise
        except urllib.error.HTTPError as error:
            # Deliberately not including the error body: it echoes the request,
            # and the request carries the key.
            status = error.code
            retriable = status == 429 or status >= 500
            if not retriable or attempt == MAX_ATTEMPTS:
                raise MissingDataError(
                    f"Gemini TTS refused the request with HTTP {status}"
                    + (" after exhausting retries" if retriable else "")
                ) from None
            pause(BACKOFF_SECONDS * attempt)
        except Exception as error:
            raise MissingDataError(
                f"Gemini TTS request failed: {type(error).__name__}"
            ) from None

    try:
        part = body["candidates"][0]["content"]["parts"][0]
        pcm = base64.b64decode(part["inlineData"]["data"])
    except (KeyError, IndexError, TypeError):
        raise MissingDataError(
            "Gemini TTS returned no audio payload; the model may have refused "
            "the text rather than failed"
        ) from None
    if not pcm:
        raise MissingDataError("Gemini TTS returned an empty audio payload")
    return wrap_pcm_as_wav(pcm)


def measure_duration(path: Path, runner: Callable | None = None) -> float:
    """Duration in seconds, read from the file rather than assumed.

    Backend-agnostic: works for whatever produced the audio, which is the point
    of measuring instead of trusting a reported figure.
    """
    command = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ]
    try:
        finished = (runner or subprocess.run)(
            command, capture_output=True, text=True, timeout=60
        )
    except FileNotFoundError:
        raise MissingDataError("ffprobe not found; it is needed to time narration")
    raw = (finished.stdout or "").strip()
    try:
        seconds = float(raw)
    except ValueError:
        raise MissingDataError(f"could not read a duration from {path}") from None
    if seconds <= 0:
        raise MissingDataError(f"{path} reports a zero duration")
    return seconds


def synthesise_beats(
    beats: list[str],
    out_dir: Path,
    speak: Callable[[str, Path], Path],
    timer: Callable[[Path], float] = measure_duration,
) -> list[Clip]:
    """One audio clip per narration beat, each timed from its own audio.

    A beat that produces no audio raises rather than being skipped: a missing
    clip would silently shorten the video and desynchronise everything after it.
    """
    if not beats:
        raise MissingDataError("no beats to narrate")
    out_dir.mkdir(parents=True, exist_ok=True)
    clips: list[Clip] = []
    for index, beat in enumerate(beats, start=1):
        path = out_dir / f"beat_{index:03d}.wav"
        speak(beat, path)
        if not path.exists() or path.stat().st_size == 0:
            raise MissingDataError(
                f"beat {index} produced no audio; a missing clip would shorten "
                "the video and desynchronise every shot after it"
            )
        clips.append(Clip(path=path, duration_s=timer(path), text=beat))
    return clips


def total_seconds(clips: list[Clip]) -> float:
    return sum(clip.duration_s for clip in clips)
