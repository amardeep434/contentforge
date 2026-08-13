from datetime import datetime, timezone

import pytest

from contentforge.errors import UnprovenancedError
from contentforge.provenance import Fact, Provenance, require_facts

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


F = Fact(value=1, provenance=PROV)


def test_require_facts_accepts_when_named_fields_are_facts():
    class Obj:
        subs = F
        title = "not a fact"

    require_facts(Obj(), "subs")  # title not checked, no raise


def test_require_facts_rejects_bare_value_in_named_field():
    class Obj:
        subs = 1234

    with pytest.raises(UnprovenancedError, match="Obj.subs is not a Fact"):
        require_facts(Obj(), "subs")


# Each fact-bearing dataclass must reject a bare int in a measured field at
# construction, since nothing type-checks these at build time.


def test_channel_stats_rejects_bare_int():
    from contentforge.providers.youtube_api import ChannelStats

    with pytest.raises(UnprovenancedError):
        ChannelStats(
            channel_id="UC1",
            title="t",
            subscribers=1234,  # bare int, not a Fact
            video_count=F,
            view_count=F,
            published_at=F,
        )


def test_video_record_rejects_bare_int():
    from contentforge.providers.youtube_api import VideoRecord

    with pytest.raises(UnprovenancedError):
        VideoRecord(
            video_id="v1",
            channel_id="UC1",
            title="t",
            published_at=F,
            view_count=99,  # bare int, not a Fact
            duration_seconds=F,
            provenance=PROV,
        )


def test_channel_facts_rejects_bare_int():
    from contentforge.research.verify import ChannelFacts

    with pytest.raises(UnprovenancedError):
        ChannelFacts(
            channel_id="UC1",
            title="t",
            subscribers=F,
            view_count=F,
            video_count=1234,  # bare int, not a Fact
            published_at=F,
        )


def test_niche_score_rejects_bare_float():
    from contentforge.research.score import NicheScore

    with pytest.raises(UnprovenancedError):
        NicheScore(
            niche="art",
            geography="US",
            score=1.0,
            rpm_usd=5.0,  # bare float, not a Fact
            sampled_channels=10,
            breakout_count=2,
            breakout_rate=0.2,
            median_lift=1.5,
            membership_factor=1.0,
        )


def test_channel_stats_accepts_all_facts():
    from contentforge.providers.youtube_api import ChannelStats

    stats = ChannelStats(
        channel_id="UC1",
        title="t",
        subscribers=F,
        video_count=F,
        view_count=F,
        published_at=F,
    )
    assert stats.subscribers is F
