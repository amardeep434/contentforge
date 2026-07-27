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


def check_citations(script: str, sources: list[Source]) -> None:
    markers = [int(n) for n in _CITATION.findall(script)]
    if not markers:
        raise ValidationError("script contains no citation markers")
    for marker in markers:
        if not 1 <= marker <= len(sources):
            raise ValidationError(
                f"script cites source {marker}, but only {len(sources)} were provided"
            )


def check_verbatim(script: str, sources: list[Source]) -> None:
    script_words = _words(script)
    window = MAX_OVERLAP_WORDS
    for index, source in enumerate(sources, start=1):
        source_words = _words(source.text)
        if len(script_words) < window or len(source_words) < window:
            continue
        source_runs = {
            tuple(source_words[i:i + window])
            for i in range(len(source_words) - window + 1)
        }
        for i in range(len(script_words) - window + 1):
            run = tuple(script_words[i:i + window])
            if run in source_runs:
                raise ValidationError(
                    f"script reproduces {window} consecutive words verbatim from "
                    f"source {index} ({source.url}): {' '.join(run)!r}"
                )


def check_credentials(script: str) -> None:
    lowered = script.lower()
    for phrase in _CREDENTIAL_CLAIMS:
        if phrase in lowered:
            raise ValidationError(f"script makes a fabricated credential claim: {phrase!r}")


def validate_script(script: str, sources: list[Source]) -> None:
    check_citations(script, sources)
    check_verbatim(script, sources)
    check_credentials(script)
