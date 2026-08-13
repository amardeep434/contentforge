"""Provenance core.

Every factual value in this pipeline is a Fact carrying the source it came from.
The guarantee is enforced two ways: Provenance validates itself on construction
(no empty source, no naive timestamp), and Fact cannot be built without a
Provenance. Stages that consume facts declare their fields as Fact, so the type
checker refuses an invented or defaulted number at the boundary — no runtime
leaf-scan needed.
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


def require_facts(obj: Any, *names: str) -> None:
    """Raise UnprovenancedError unless each named field of obj is a Fact.

    The runtime teeth behind the Fact type. Dataclasses here mix Facts with
    plain strings (a title is not a measurement), so the check is selective:
    only the fields that carry retrieved values are asserted, by name.
    """
    for name in names:
        if not isinstance(getattr(obj, name), Fact):
            raise UnprovenancedError(f"{type(obj).__name__}.{name} is not a Fact")
