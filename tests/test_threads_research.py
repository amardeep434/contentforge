"""Threads reading via Jina Reader.

The parser is the whole risk surface here: Jina returns loose markdown, and a
parser that silently yields nothing looks identical to an account with no posts.
These tests exist mostly to pin that distinction down.
"""

from datetime import datetime, timezone

import pytest

from contentforge.errors import MissingDataError
from contentforge.providers.threads_research import (
    read_thread,
    parse_posts,
    profile_url,
    search_url,
    read_profile,
    search_threads,
)

NOW = datetime(2026, 7, 30, tzinfo=timezone.utc)

SAMPLE = """Title: Search • Threads

URL Source: https://www.threads.net/search?q=faceless%20youtube

Markdown Content:
[](https://www.threads.net/)

[![Image 1: pic](https://cdn.example/a.jpg)](https://www.threads.net/@onlinemoneyai1)

[onlinemoneyai1](https://www.threads.net/@onlinemoneyai1)

[04/25/25](https://www.threads.net/@onlinemoneyai1/post/DI4jWJoyuNT)

Daily Youtube Automation Faceless Channel Idea: made $3,084 in 28 days.

1.1K

274

167

66

[secondposter](https://www.threads.net/@secondposter)

[05/01/25](https://www.threads.net/@secondposter/post/ABC123xyz01)

A second post body that is long enough to be considered real content here.

12

3
"""


def test_parses_author_permalink_and_text():
    posts = parse_posts(SAMPLE, "https://x", NOW)
    assert len(posts) == 2
    first = posts[0]
    assert first.author == "onlinemoneyai1"
    assert first.permalink == "https://www.threads.net/@onlinemoneyai1/post/DI4jWJoyuNT"
    assert "3,084" in first.text
    assert first.posted_on == "04/25/25"


def test_carries_retrieval_provenance():
    posts = parse_posts(SAMPLE, "https://query-url", NOW)
    assert all(p.retrieved_at == NOW for p in posts)
    assert all(p.source_url == "https://query-url" for p in posts)


def test_engagement_counts_are_not_mistaken_for_post_text():
    # "1.1K" / "274" sit on their own lines under each post. Treating them as
    # body text would put junk into every record.
    posts = parse_posts(SAMPLE, "https://x", NOW)
    assert "1.1K" not in posts[0].text
    assert posts[1].text.startswith("A second post body")


def test_empty_page_raises_rather_than_returning_nothing():
    # An account with no posts and a parser that broke look identical unless
    # this is an error. Silence here would be indistinguishable from "no data".
    with pytest.raises(MissingDataError):
        parse_posts("Title: Search • Threads\n\nMarkdown Content:\n", "https://x", NOW)


def test_urls_are_encoded():
    assert "faceless%20youtube" in search_url("faceless youtube")
    assert "%26" in search_url("a&b")  # or the & would start a new query param
    assert profile_url("@zuck") == profile_url("zuck")
    assert profile_url("zuck").endswith("/@zuck")


def test_transport_receives_the_canonical_threads_url_not_the_proxy():
    # Provenance must record the URL a human can open to check the claim. Jina
    # is a fetch mechanism, not the source, so the reader prefix belongs inside
    # http_get and never in the recorded source_url.
    calls = []

    def transport(url):
        calls.append(url)
        return SAMPLE

    posts = read_profile("onlinemoneyai1", transport=transport, now=NOW)
    assert calls == ["https://www.threads.net/@onlinemoneyai1"]
    assert posts[0].source_url == "https://www.threads.net/@onlinemoneyai1"
    assert posts[0].author == "onlinemoneyai1"


def test_search_uses_injected_transport():
    posts = search_threads("faceless youtube", transport=lambda u: SAMPLE, now=NOW)
    assert len(posts) == 2


def test_transport_failure_propagates_as_missing_data():
    def boom(url):
        raise OSError("connection reset")

    with pytest.raises(MissingDataError):
        search_threads("x", transport=boom, now=NOW)


LEAKY = """Markdown Content:
[youtubecreators](https://www.threads.net/@youtubecreators)

[12h](https://www.threads.net/@youtubecreators/post/DbY6H9rCTxG)

what's a hard truth you wish someone told you? ](https://www.threads.net/@youtubecreators)

143

44

[youtubecreators](https://www.threads.net/@youtubecreators)

[1d](https://www.threads.net/@youtubecreators/post/DbWd4H-FC5D)

don't fear the edit.

Log in to see more from youtubecreators.

Log in or sign up for Threads

See what people are talking about and join the conversation.
"""


def test_orphan_link_fragments_are_stripped():
    # Jina sometimes splits a markdown link across lines, leaving a bare
    # "](url)" tail that would otherwise be recorded as post text.
    posts = parse_posts(LEAKY, "https://x", NOW)
    assert posts[0].text == "what's a hard truth you wish someone told you?"
    assert "](" not in posts[0].text


def test_login_wall_is_not_treated_as_post_content():
    # Threads shows ~4 posts then a login prompt. That prompt is chrome, not
    # the last post's body, and silently appending it corrupts the record.
    posts = parse_posts(LEAKY, "https://x", NOW)
    assert posts[-1].text == "don't fear the edit."
    assert "Log in" not in posts[-1].text


WITH_IMAGE = """Markdown Content:
[onlinemoneyai1](https://www.threads.net/@onlinemoneyai1)

[04/25/25](https://www.threads.net/@onlinemoneyai1/post/DI4jWJoyuNT)

Made $3,084 in 28 days.

[![Image 2](https://scontent-sea5-1.cdninstagram.com/v/t51.75761-15/shot.jpg?stp=x)](https://www.threads.net/@onlinemoneyai1/post/DI4jWJoyuNT)

143
"""


def test_post_images_are_captured():
    # The channel name is routinely inside a Studio screenshot rather than the
    # caption, so a text-only record makes a verifiable claim look unverifiable.
    posts = parse_posts(WITH_IMAGE, "https://x", NOW)
    assert posts[0].images == (
        "https://scontent-sea5-1.cdninstagram.com/v/t51.75761-15/shot.jpg?stp=x",
    )


def test_image_urls_do_not_leak_into_text():
    posts = parse_posts(WITH_IMAGE, "https://x", NOW)
    assert posts[0].text == "Made $3,084 in 28 days."
    assert "cdninstagram" not in posts[0].text


def test_posts_without_images_get_an_empty_tuple():
    posts = parse_posts(SAMPLE, "https://x", NOW)
    assert posts[0].images == ()


THREAD = """Markdown Content:
[adamdelduca](https://www.threads.net/@adamdelduca)

[07/14/26](https://www.threads.net/@adamdelduca/post/ROOT01)

Here's how I did it:

431

[adamdelduca](https://www.threads.net/@adamdelduca)

[07/14/26](https://www.threads.net/@adamdelduca/post/STEP01)

·Author

[![Image 4](https://scontent-sea1-1.cdninstagram.com/v/step1.jpg?x=1)](https://www.threads.net/@adamdelduca/post/STEP01)

7

[somecommenter](https://www.threads.net/@somecommenter)

[07/14/26](https://www.threads.net/@somecommenter/post/REPLY1)

nice post

2
"""


def test_read_thread_returns_root_and_replies():
    posts = read_thread("https://p", transport=lambda u: THREAD, now=NOW)
    assert [p.permalink.rsplit("/", 1)[1] for p in posts] == [
        "ROOT01",
        "STEP01",
        "REPLY1",
    ]


def test_author_replies_carry_the_step_images():
    # The steps are screenshots posted as replies; their text is often empty,
    # so the images are the payload.
    posts = read_thread("https://p", transport=lambda u: THREAD, now=NOW)
    steps = [p for p in posts if p.author == posts[0].author][1:]
    assert len(steps) == 1
    assert steps[0].images == ("https://scontent-sea1-1.cdninstagram.com/v/step1.jpg?x=1",)


def test_commenters_are_distinguishable_from_the_author():
    posts = read_thread("https://p", transport=lambda u: THREAD, now=NOW)
    assert posts[-1].author == "somecommenter"


def test_profile_pictures_are_not_collected_as_evidence():
    markdown = """Markdown Content:
[a](https://www.threads.net/@a)

[1d](https://www.threads.net/@a/post/P1)

body

[![Image 5: a's profile picture](https://scontent-x.cdninstagram.com/avatar.jpg)](x)

[![Image 6](https://scontent-x.cdninstagram.com/real-screenshot.jpg)](x)
"""
    posts = parse_posts(markdown, "https://x", NOW)
    assert posts[0].images == ("https://scontent-x.cdninstagram.com/real-screenshot.jpg",)
