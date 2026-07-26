"""Provenance core.

Every factual value in this pipeline is a Fact carrying the source it came from.
`require_provenance` is the gate between stages: it refuses anything whose leaves
are not Facts, so an invented or defaulted number cannot travel downstream
disguised as retrieved data.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from contentforge.errors import UnprovenancedError


@dataclass(frozen=True)
class Provenance:
    """Where a value came from, and when."""

    source_url: str
    response_id: str
    retrieved_at: datetime

    def __post_init__(self) -> None:
        if not self.source_url:
            raise UnprovenancedError("source_url must not be empty")
        if not self.response_id:
            raise UnprovenancedError("response_id must not be empty")
        if self.retrieved_at.tzinfo is None:
            raise UnprovenancedError("retrieved_at must be timezone-aware")


@dataclass(frozen=True)
class Fact:
    """A value bound to its source."""

    value: Any
    provenance: Provenance


def require_provenance(obj: Any) -> None:
    """Raise UnprovenancedError unless every leaf of obj is a Fact."""
    if isinstance(obj, Fact):
        return
    if isinstance(obj, dict):
        for value in obj.values():
            require_provenance(value)
        return
    if isinstance(obj, (list, tuple, set)):
        for item in obj:
            require_provenance(item)
        return
    raise UnprovenancedError(f"value without provenance: {obj!r}")
