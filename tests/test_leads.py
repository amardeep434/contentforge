"""The lead loop: claims in, checked facts out."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from contentforge.errors import MissingDataError
from contentforge.providers.threads_research import ThreadsPost
from contentforge.research.leads import (
    Lead,
    add_image_handles,
    extract_handles,
    gather_leads,
    load_leads,
    money_in,
    profile_views,
    save_leads,
    write_report,
)

NOW = datetime(2026, 7, 30, tzinfo=timezone.utc)


def post(author="poster", text="", images=(), pid="AAA111"):
    return ThreadsPost(
        author=author,
        permalink=f"https://www.threads.net/@{author}/post/{pid}",
        posted_on="04/25/25",
        text=text,
        images=tuple(images),
        source_url="https://query",
        retrieved_at=NOW,
    )


def test_extracts_handles_from_urls_and_bare_mentions():
    text = "check youtube.com/@eonatlas and also @someunfilteredguy"
    assert extract_handles(text) == ("eonatlas", "someunfilteredguy")


def test_excludes_the_posters_own_handle():
    # The poster's own handle appears constantly and is almost never the
    # channel being discussed.
    assert extract_handles("I'm @wannercashcow", exclude="wannercashcow") == ()


def test_money_is_detected_so_dead_leads_can_be_counted():
    assert money_in("made $3,084 and 308K subs") == ("$3,084", "308K subs")
    assert money_in("no numbers here") == ()


def test_gather_downloads_images_and_records_paths(tmp_path):
    grabbed = []

    def fetch(url, destination):
        grabbed.append(url)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"jpg")
        return destination

    leads = gather_leads(
        "q",
        tmp_path,
        search=lambda q, serp_type: [post(images=("https://cdn/a.jpg",), text="$100")],
        fetch_image=fetch,
    )
    assert grabbed == ["https://cdn/a.jpg"]
    assert len(leads[0].image_paths) == 1
    assert Path(leads[0].image_paths[0]).read_bytes() == b"jpg"


def test_a_post_whose_images_fail_is_still_recorded(tmp_path):
    # Losing the claim and its permalink because a CDN 403'd would understate
    # how much of the source could not be read.
    def broken(url, destination):
        raise OSError("403")

    leads = gather_leads(
        "q",
        tmp_path,
        search=lambda q, serp_type: [post(text="made $500", images=("https://x",))],
        fetch_image=broken,
    )
    assert len(leads) == 1
    assert leads[0].image_paths == ()
    assert leads[0].money_mentioned == ("$500",)


def test_round_trip_through_disk(tmp_path):
    leads = gather_leads(
        "q", tmp_path, search=lambda q, serp_type: [post(text="hi @eonatlas")]
    )
    save_leads(leads, tmp_path, "q", NOW)
    query, loaded = load_leads(tmp_path)
    assert query == "q"
    assert loaded == leads


def test_loading_before_gathering_is_an_error(tmp_path):
    with pytest.raises(MissingDataError):
        load_leads(tmp_path)


def test_image_handles_are_merged_without_losing_text_handles(tmp_path):
    leads = gather_leads(
        "q", tmp_path, search=lambda q, serp_type: [post(text="see @fromtext")]
    )
    save_leads(leads, tmp_path, "q", NOW)
    updated = add_image_handles(tmp_path, {leads[0].permalink: ["fromimage"]})
    assert updated[0].all_handles == ("fromtext", "fromimage")
    # and it survives a reload
    _, reloaded = load_leads(tmp_path)
    assert reloaded[0].handles_from_images == ("fromimage",)


def test_unread_screenshots_are_distinct_from_read_and_empty(tmp_path):
    leads = gather_leads("q", tmp_path, search=lambda q, serp_type: [post()])
    assert leads[0].handles_from_images == ()
    save_leads(leads, tmp_path, "q", NOW)
    record = json.loads((tmp_path / "leads.json").read_text())
    assert record["leads"][0]["handles_from_images"] == []


def test_profile_reports_median_skew_and_hit_rate():
    p = profile_views([1_000, 2_000, 500_000])
    assert p["median"] == 2_000
    assert p["mean"] == 167_667
    assert p["skew"] == 83.83  # the exact distortion C-001 is about
    assert p["hit_rate"] == 33.3


def test_repeatable_requires_all_three_conditions():
    steady = profile_views([120_000] * 10)
    assert steady["repeatable"] is True
    # same hit-rate, too few videos to mean anything
    assert profile_views([120_000] * 5)["repeatable"] is False
    # one viral hit carrying flops
    assert profile_views([100] * 9 + [5_000_000])["repeatable"] is False


def test_profiling_nothing_raises():
    with pytest.raises(MissingDataError):
        profile_views([])


def test_report_counts_uncheckable_claims(tmp_path):
    leads = [
        Lead("a", "p1", "d", "made $50,000", ("$50,000",), (), ()),
        Lead("b", "p2", "d", "see @chan", (), ("chan",), ()),
    ]
    path = write_report(
        [
            {
                "handle": "chan",
                "subs": 1000,
                "n": 9,
                "median": 5000,
                "skew": 1.2,
                "hit_rate": 0.0,
                "repeatable": False,
                "permalink": "p2",
            }
        ],
        leads,
        tmp_path,
        "q",
    )
    text = path.read_text()
    assert "monetary claims naming no channel (uncheckable): 1" in text
    assert "made $50,000" in text
    assert "@chan" in text


def test_expansion_pulls_step_images_from_author_replies(tmp_path):
    root = post(author="guru", text="made $6,000 — here's how:", pid="ROOT")
    step = post(author="guru", images=("https://cdn/step1.jpg",), pid="STEP")
    noise = post(author="rando", images=("https://cdn/spam.jpg",), pid="RND")

    def fetch(url, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"x")
        return destination

    leads = gather_leads(
        "q",
        tmp_path,
        search=lambda q, serp_type: [root],
        fetch_image=fetch,
        expand=lambda permalink: [root, step, noise],
    )
    # only the author's own replies are steps; a commenter's image is not
    assert len(leads[0].reply_image_paths) == 1
    assert "reply1" in leads[0].reply_image_paths[0]


def test_expansion_failure_does_not_lose_the_lead(tmp_path):
    def boom(permalink):
        raise OSError("render timeout")

    leads = gather_leads(
        "q",
        tmp_path,
        search=lambda q, serp_type: [post(text="made $500")],
        expand=boom,
    )
    assert len(leads) == 1
    assert leads[0].reply_image_paths == ()
