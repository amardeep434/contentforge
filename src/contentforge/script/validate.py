"""The policy gate.

YouTube's inauthentic-content policy disqualifies "readings of other materials you
did not create" and "mass-produced templates". Shape rotation handles the second.
This module handles the first, plus the fabricated-authority filler LLMs produce
by default ("I've spent years studying this").

Treated as security code: adversarial tests, hard failure rather than a warning.
"""

import re

from contentforge.errors import ContentforgeError
from contentforge.sourcing.fetch import Source

# Longest run of consecutive words a script may share with any source. Twelve is a
# starting value — long enough for unavoidable technical phrasing, short enough that
# a lifted sentence trips it. Tune against real scripts, never upward without cause.
MAX_OVERLAP_WORDS = 12

_CITATION = re.compile(r"\[(\d+)\]")
_WORD = re.compile(r"[a-z0-9]+")

_CREDENTIAL_CLAIMS = (
    "i have spent", "i've spent", "i have studied", "i've studied",
    "in my experience", "i have analysed", "i have analyzed",
    "i've analysed", "i've analyzed", "years of research",
    "i have interviewed", "i've interviewed",
)


class ValidationError(ContentforgeError):
    """The script violates a publication rule."""


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _citation_violations(script: str, sources: list[Source]) -> list[str]:
    markers = [int(n) for n in _CITATION.findall(script)]
    if not markers:
        return ["script contains no citation markers"]
    return [
        f"script cites source {marker}, but only {len(sources)} were provided"
        for marker in markers
        if not 1 <= marker <= len(sources)
    ]


def _verbatim_violations(script: str, sources: list[Source]) -> list[str]:
    """Every maximal lifted span, reported once. Sliding 12-word windows over a
    lifted sentence all match; merging adjacent matches into one span keeps the
    feedback to 'you lifted this phrase' instead of a wall of near-duplicates."""
    script_words = _words(script)
    window = MAX_OVERLAP_WORDS
    violations: list[str] = []
    for index, source in enumerate(sources, start=1):
        source_words = _words(source.text)
        if len(script_words) < window or len(source_words) < window:
            continue
        source_runs = {
            tuple(source_words[i:i + window])
            for i in range(len(source_words) - window + 1)
        }
        starts = [
            i for i in range(len(script_words) - window + 1)
            if tuple(script_words[i:i + window]) in source_runs
        ]
        for start, end in _merge_windows(starts, window):
            phrase = " ".join(script_words[start:end])
            violations.append(
                f"script reproduces {end - start} consecutive words verbatim from "
                f"source {index} ({source.url}): {phrase!r}"
            )
    return violations


def _merge_windows(starts: list[int], window: int) -> list[tuple[int, int]]:
    """Collapse overlapping/adjacent match windows into [start, end) word spans."""
    spans: list[tuple[int, int]] = []
    for start in starts:
        end = start + window
        if spans and start <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], end))
        else:
            spans.append((start, end))
    return spans


def _credential_violations(script: str) -> list[str]:
    lowered = script.lower()
    return [
        f"script makes a fabricated credential claim: {phrase!r}"
        for phrase in _CREDENTIAL_CLAIMS
        if phrase in lowered
    ]


def find_violations(script: str, sources: list[Source]) -> list[str]:
    """Every publication-rule violation in the script, not just the first. An
    empty list means the script is clean. The feedback that lets the scriptwriter
    self-correct (runtime.scriptwriter) and the one-shot report both build on it."""
    return (
        _citation_violations(script, sources)
        + _verbatim_violations(script, sources)
        + _credential_violations(script)
    )


def check_citations(script: str, sources: list[Source]) -> None:
    violations = _citation_violations(script, sources)
    if violations:
        raise ValidationError(violations[0])


def check_verbatim(script: str, sources: list[Source]) -> None:
    violations = _verbatim_violations(script, sources)
    if violations:
        raise ValidationError(violations[0])


def check_credentials(script: str) -> None:
    violations = _credential_violations(script)
    if violations:
        raise ValidationError(violations[0])


def validate_script(script: str, sources: list[Source]) -> None:
    violations = find_violations(script, sources)
    if violations:
        raise ValidationError("; ".join(violations))
