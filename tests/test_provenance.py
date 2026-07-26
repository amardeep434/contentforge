from datetime import datetime, timezone

import pytest

from contentforge.errors import UnprovenancedError
from contentforge.provenance import Fact, Provenance, require_provenance

PROV = Provenance(
    source_url="https://www.googleapis.com/youtube/v3/channels?id=UC123",
    response_id="resp-abc",
    retrieved_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
)


def test_fact_carries_provenance():
    fact = Fact(value=1234, provenance=PROV)
    assert fact.value == 1234
    assert fact.provenance.response_id == "resp-abc"


def test_fact_is_immutable():
    fact = Fact(value=1, provenance=PROV)
    with pytest.raises(Exception):
        fact.value = 2


def test_provenance_rejects_blank_source_url():
    with pytest.raises(UnprovenancedError):
        Provenance(source_url="", response_id="r", retrieved_at=PROV.retrieved_at)


def test_provenance_rejects_blank_response_id():
    with pytest.raises(UnprovenancedError):
        Provenance(source_url="https://x", response_id="", retrieved_at=PROV.retrieved_at)


def test_provenance_rejects_naive_datetime():
    with pytest.raises(UnprovenancedError):
        Provenance(
            source_url="https://x", response_id="r", retrieved_at=datetime(2026, 7, 26)
        )


def test_require_provenance_accepts_fact():
    require_provenance(Fact(value=1, provenance=PROV))


def test_require_provenance_rejects_bare_value():
    with pytest.raises(UnprovenancedError):
        require_provenance(1234)


def test_require_provenance_recurses_into_containers():
    require_provenance([Fact(value=1, provenance=PROV), Fact(value=2, provenance=PROV)])
    with pytest.raises(UnprovenancedError):
        require_provenance([Fact(value=1, provenance=PROV), 2])


def test_require_provenance_recurses_into_dict_values():
    with pytest.raises(UnprovenancedError):
        require_provenance({"subs": Fact(value=1, provenance=PROV), "views": 99})


def test_require_provenance_rejects_none():
    with pytest.raises(UnprovenancedError):
        require_provenance(None)
