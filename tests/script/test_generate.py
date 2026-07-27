from datetime import datetime, timezone

import pytest

from contentforge.errors import MissingDataError
from contentforge.providers.llm import LLMClient
from contentforge.script.generate import SHAPES, choose_shape, generate_script
from contentforge.sourcing.fetch import Source

NOW = datetime(2026, 7, 27, tzinfo=timezone.utc)
SOURCES = [Source("https://a", "A", "Hot air circulates rapidly.", NOW)]


def test_shape_never_repeats_the_previous_one():
    for previous in SHAPES:
        assert choose_shape("air fryers", previous) != previous


def test_shape_is_deterministic_for_a_topic():
    assert choose_shape("air fryers") == choose_shape("air fryers")


def test_different_topics_can_get_different_shapes():
    assert len({choose_shape(t) for t in ("air fryers", "gps", "vaccines", "lithium batteries")}) > 1


def test_prompt_carries_the_source_text_and_urls():
    seen = {}

    def transport(url, payload, headers):
        seen["user"] = payload["messages"][1]["content"]
        return {"choices": [{"message": {"content": "script [1]"}}]}

    generate_script(LLMClient("http://x/v1", "", "m", transport), "air fryers", SOURCES, SHAPES[0])
    assert "Hot air circulates rapidly." in seen["user"]
    assert "https://a" in seen["user"]


def test_no_sources_raises_before_calling_the_model():
    calls = []

    def transport(url, payload, headers):
        calls.append(1)
        return {"choices": [{"message": {"content": "x"}}]}

    with pytest.raises(MissingDataError):
        generate_script(LLMClient("http://x/v1", "", "m", transport), "air fryers", [], SHAPES[0])
    assert calls == [], "must not spend a model call on an ungrounded script"
