"""Reddit posts must arrive in the same shape the lead loop already consumes."""

import json
from datetime import datetime, timezone

import pytest

from contentforge.errors import MissingDataError
from contentforge.providers.reddit_research import (
    parse_posts,
    search_reddit,
)

NOW = datetime(2026, 7, 30, tzinfo=timezone.utc)

PAYLOAD = json.dumps(
    [
        {
            "id": "abc",
            "title": "How I'd Start a Faceless YouTube Channel",
            "subreddit": "r/aitubers",
            "author": "No_Entertainer_9655",
            "score": 212,
            "comments": 65,
            "url": "https://www.reddit.com/r/aitubers/comments/abc/x/",
            "created_utc": 1783494131,
            "selftext": "Your niche matters more than the tools. I made $3,084.",
            "preview_image_url": "https://i.redd.it/shot.jpg",
            "gallery_urls": ["https://i.redd.it/two.jpg"],
        }
    ]
)


def test_title_and_body_both_reach_the_text():
    post = parse_posts(PAYLOAD, "src", NOW)[0]
    assert post.title in post.text
    assert "$3,084" in post.text


def test_title_comes_first_so_a_truncated_read_still_makes_sense():
    assert parse_posts(PAYLOAD, "src", NOW)[0].text.startswith("How I'd Start")


def test_engagement_is_kept_as_a_quality_signal():
    post = parse_posts(PAYLOAD, "src", NOW)[0]
    assert post.score == 212
    assert post.comments == 65
    assert post.subreddit == "r/aitubers"


def test_created_utc_becomes_a_readable_date():
    assert parse_posts(PAYLOAD, "src", NOW)[0].posted_on == "2026-07-08"


def test_preview_and_gallery_images_are_both_collected():
    assert parse_posts(PAYLOAD, "src", NOW)[0].images == (
        "https://i.redd.it/shot.jpg",
        "https://i.redd.it/two.jpg",
    )


def test_shape_matches_what_gather_leads_consumes():
    # gather_leads is duck-typed over these five attributes; a rename here would
    # break the lead loop silently.
    post = parse_posts(PAYLOAD, "src", NOW)[0]
    for attribute in ("author", "permalink", "posted_on", "text", "images"):
        assert hasattr(post, attribute)


def test_empty_results_raise_rather_than_returning_nothing():
    with pytest.raises(MissingDataError):
        parse_posts("[]", "src", NOW)


def test_unparseable_output_raises():
    with pytest.raises(MissingDataError):
        parse_posts("Usage: opencli reddit search", "src", NOW)


def test_a_missing_timestamp_does_not_crash_the_run():
    payload = json.dumps([{"title": "t", "url": "u", "created_utc": None}])
    assert parse_posts(payload, "src", NOW)[0].posted_on == ""


def test_search_passes_subreddit_and_sort_through():
    captured = {}

    def runner(args):
        captured["args"] = args
        return PAYLOAD

    search_reddit("faceless", runner=runner, subreddit="aitubers", sort="top", now=NOW)
    assert "--subreddit" in captured["args"]
    assert "aitubers" in captured["args"]
    assert "top" in captured["args"]
    assert "json" in captured["args"]


def test_serp_type_is_accepted_and_ignored_for_signature_compatibility():
    # gather_leads calls search(query, serp_type=...) for either source.
    posts = search_reddit("q", runner=lambda a: PAYLOAD, now=NOW, serp_type="tags")
    assert len(posts) == 1
