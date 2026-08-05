"""YouTube metadata: generated from the script, clamped to YouTube's limits."""

import json

import pytest

from contentforge.errors import MissingDataError
from contentforge.publish.metadata import (
    MAX_TAGS_TOTAL,
    MAX_TITLE,
    Metadata,
    generate_metadata,
    parse_metadata,
)


def payload(title="How ceiling fans really work", description="They move air.",
            tags=None):
    return json.dumps({"title": title, "description": description,
                       "tags": tags if tags is not None else ["fans", "cooling"]})


class Source:
    def __init__(self, url):
        self.url = url


def test_a_clean_response_parses():
    meta = parse_metadata(payload())
    assert meta.title == "How ceiling fans really work"
    assert meta.tags == ("fans", "cooling")


def test_a_code_fence_is_tolerated():
    meta = parse_metadata("```json\n" + payload() + "\n```")
    assert meta.title.startswith("How ceiling")


def test_a_title_over_the_limit_is_rejected():
    with pytest.raises(MissingDataError, match="YouTube rejects"):
        parse_metadata(payload(title="x" * (MAX_TITLE + 1)))


def test_a_missing_title_raises():
    with pytest.raises(MissingDataError, match="no title"):
        parse_metadata(payload(title="  "))


def test_a_missing_description_raises():
    with pytest.raises(MissingDataError, match="no description"):
        parse_metadata(payload(description=""))


def test_tags_are_lowercased_and_whitespace_collapsed():
    meta = parse_metadata(payload(tags=["Ceiling Fans", "  AIR   flow "]))
    assert meta.tags == ("ceiling fans", "air flow")


def test_tags_are_clamped_to_the_total_budget():
    # A long tail of tags would truncate at insert time; drop the overflow so
    # the kept tags stay whole.
    many = [f"tag number {n}" for n in range(200)]
    meta = parse_metadata(payload(tags=many))
    assert sum(len(t) + 1 for t in meta.tags) <= MAX_TAGS_TOTAL
    assert all(t in {f"tag number {n}" for n in range(200)} for t in meta.tags)


def test_the_source_urls_are_appended_to_the_description():
    meta = parse_metadata(payload(), sources=[Source("https://a.example"),
                                              Source("https://b.example")])
    assert "Sources:" in meta.description
    assert "https://a.example" in meta.description
    assert "https://b.example" in meta.description


def test_dict_sources_are_also_accepted():
    meta = parse_metadata(payload(), sources=[{"url": "https://c.example"}])
    assert "https://c.example" in meta.description


def test_malformed_json_raises():
    with pytest.raises(MissingDataError, match="not valid JSON"):
        parse_metadata("{oops}")


def test_a_response_with_no_object_raises():
    with pytest.raises(MissingDataError, match="no JSON object"):
        parse_metadata("I cannot help with that.")


def test_generation_sends_the_script():
    seen = {}

    class FakeClient:
        def complete(self, system, user, max_tokens=0):
            seen["user"] = user
            return payload()

    generate_metadata(FakeClient(), "A ceiling fan moves air but never cools it.")
    assert "ceiling fan" in seen["user"]


def test_generation_refuses_an_empty_script():
    class FakeClient:
        def complete(self, *a, **k):
            return payload()

    with pytest.raises(MissingDataError, match="no script"):
        generate_metadata(FakeClient(), "   ")


def test_a_short_thumbnail_headline_is_produced():
    from contentforge.publish.metadata import MAX_THUMB_WORDS
    raw = json.dumps({"title": "The Economics of Owning a Gym", "description": "x.",
                      "tags": ["a"], "thumb_headline": "IT IS NOT A GYM"})
    meta = parse_metadata(raw)
    assert len(meta.thumb_headline.split()) <= MAX_THUMB_WORDS


def test_a_missing_thumb_headline_falls_back_to_the_title():
    meta = parse_metadata(payload(title="The Economics of Owning a Gym"))
    assert meta.thumb_headline                      # never empty
    assert len(meta.thumb_headline.split()) <= 4


def test_an_overlong_thumb_headline_is_replaced_not_kept():
    raw = json.dumps({"title": "Short Title Here", "description": "x.", "tags": ["a"],
                      "thumb_headline": "one two three four five six seven"})
    meta = parse_metadata(raw)
    assert len(meta.thumb_headline.split()) <= 4
