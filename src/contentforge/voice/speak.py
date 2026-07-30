"""Narration via edge-tts.

Free, no key, no quota — Microsoft's Edge read-aloud voices over a websocket.

Two responsibilities:

**Never speak a citation marker.** `[1]` exists for the validator and the video
description. Spoken aloud it is noise, and a narrator saying "one" mid-sentence
is the kind of detail that reads as automated.

**Report where each word lands.** edge-tts emits `WordBoundary` events, so the
visuals can be cut against the actual narration instead of against an estimate.
Task 3 requires shot durations to sum to the narration duration; without real
timings that can only be guessed, and a guess drifts.

Offsets arrive in 100-nanosecond ticks, the same unit SSML uses.
"""

import asyncio
import re
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Callable

from contentforge.errors import MissingDataError

DEFAULT_VOICE = "en-GB-RyanNeural"

#: The exemplar narrates at ~142 words per minute, measured across 2,592 words
#: of its Cezanne video. edge-tts at default rate runs ~162 wpm, so it is slowed
#: to match. Pace is one of the few narration properties that can be measured
#: rather than judged by ear.
DEFAULT_RATE = "-12%"
EXEMPLAR_WPM = 142

#: edge-tts reports offsets and durations in 100ns ticks, as SSML does.
TICKS_PER_SECOND = 10_000_000

#: Only bracketed *numbers* are citation markers. "[sic]" is editorial and must
#: survive; stripping every bracket would silently rewrite the script.
_CITATION = re.compile(r"\s*\[\d+\]")

#: A stripped marker can leave a space before punctuation — "food ." — which the
#: narrator pauses on audibly.
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([.,;:!?])")


@dataclass(frozen=True)
class WordTiming:
    word: str
    start_s: float
    duration_s: float

    @property
    def end_s(self) -> float:
        return self.start_s + self.duration_s


@dataclass(frozen=True)
class Narration:
    path: Path
    duration_s: float
    words: tuple[WordTiming, ...]

    @property
    def length(self) -> timedelta:
        return timedelta(seconds=self.duration_s)

    @property
    def wpm(self) -> float:
        """Speech rate, for comparison against the exemplar's 142."""
        return words_per_minute(len(self.words), self.duration_s)


def to_seconds(ticks: int) -> float:
    return ticks / TICKS_PER_SECOND


def strip_citations(text: str) -> str:
    """Remove citation markers, leaving text a narrator can read cleanly."""
    stripped = _SPACE_BEFORE_PUNCT.sub(r"\1", _CITATION.sub("", text or ""))
    stripped = re.sub(r"\s{2,}", " ", stripped).strip()
    if not stripped:
        raise MissingDataError(
            "nothing left to narrate after removing citation markers; "
            "synthesising silence would produce a video with no narration"
        )
    return stripped


def words_per_minute(word_count: int, seconds: float) -> float:
    if seconds <= 0:
        raise MissingDataError("cannot compute a speech rate over zero seconds")
    return word_count / seconds * 60


def edge_runner(
    text: str, voice: str, rate: str = DEFAULT_RATE
) -> tuple[bytes, list[dict]]:
    """Stream one utterance from edge-tts, returning audio and boundary events."""
    import edge_tts

    async def _run():
        audio = bytearray()
        events: list[dict] = []
        # edge-tts >=7 defaults to SentenceBoundary and then emits no
        # WordBoundary events at all. Word-level timings are requested
        # explicitly; sentence boundaries can be derived from them, not the
        # other way round.
        communicate = edge_tts.Communicate(
            text, voice, rate=rate, boundary="WordBoundary"
        )
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio" and chunk.get("data"):
                audio.extend(chunk["data"])
            elif chunk.get("type") == "WordBoundary":
                events.append(chunk)
        return bytes(audio), events

    return asyncio.run(_run())


def _write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def synthesise(
    text: str,
    out_path: Path,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
    runner: Callable[..., tuple[bytes, list[dict]]] = edge_runner,
    writer: Callable[[Path, bytes], Path] = _write,
) -> Narration:
    """Narrate `text` to `out_path`, returning audio plus word timings."""
    spoken = strip_citations(text)
    try:
        audio, events = runner(spoken, voice, rate)
    except MissingDataError:
        raise
    except Exception as error:
        raise MissingDataError(
            f"speech synthesis failed: {type(error).__name__}"
        ) from None

    if not audio:
        raise MissingDataError(
            "speech synthesis returned no audio; a zero-byte file renders as a "
            "silent video, which looks like success"
        )

    words = tuple(
        WordTiming(
            word=event.get("text", ""),
            start_s=to_seconds(event.get("offset", 0)),
            duration_s=to_seconds(event.get("duration", 0)),
        )
        for event in events
        if event.get("type") == "WordBoundary"
    )
    if not words:
        raise MissingDataError(
            "speech synthesis returned no word boundaries, so the visuals cannot "
            "be cut against the narration; guessing durations drifts out of sync"
        )

    writer(out_path, audio)
    return Narration(path=out_path, duration_s=words[-1].end_s, words=words)
