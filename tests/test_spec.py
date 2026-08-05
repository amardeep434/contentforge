"""Per-beat visual specification: what is drawn and what is lettered."""

import json

import pytest

from contentforge.errors import MissingDataError
from contentforge.script.spec import (
    MAX_CHECKLIST_ITEMS,
    BeatSpec,
    caption_lines,
    generate_spec,
    parse_spec,
)


def entry(subject="a wooden chair", heading="", checklist=None):
    return {"subject": subject, "heading": heading, "checklist": checklist or []}


def test_one_spec_per_beat():
    specs = parse_spec(json.dumps([entry(), entry("a rusted hinge")]), ["one.", "two."])
    assert [s.subject for s in specs] == ["a wooden chair", "a rusted hinge"]
    assert [s.text for s in specs] == ["one.", "two."]


def test_a_short_spec_raises_rather_than_leaving_a_beat_blank():
    # Truncating would render as a held black frame partway through the video.
    with pytest.raises(MissingDataError, match="nothing on screen"):
        parse_spec(json.dumps([entry()]), ["one.", "two."])


def test_a_code_fence_around_the_json_is_tolerated():
    raw = "```json\n" + json.dumps([entry()]) + "\n```"
    assert parse_spec(raw, ["one."])[0].subject == "a wooden chair"


def test_prose_either_side_of_the_array_is_tolerated():
    raw = "Sure, here you go:\n" + json.dumps([entry()]) + "\nHope that helps!"
    assert parse_spec(raw, ["one."])[0].subject == "a wooden chair"


def test_a_response_with_no_array_raises():
    with pytest.raises(MissingDataError, match="no JSON array"):
        parse_spec("I cannot help with that.", ["one."])


def test_malformed_json_raises():
    with pytest.raises(MissingDataError, match="not valid JSON"):
        parse_spec("[{oops}]", ["one."])


def test_an_entry_with_nothing_to_draw_raises():
    with pytest.raises(MissingDataError, match="nothing to draw"):
        parse_spec(json.dumps([entry(subject="  ")]), ["one."])


def test_lettering_is_upper_cased_to_match_the_reference():
    specs = parse_spec(
        json.dumps([entry(heading="legal requirement", checklist=["air intake"])]),
        ["one."],
    )
    assert specs[0].heading == "LEGAL REQUIREMENT"
    assert specs[0].checklist == ("AIR INTAKE",)


def test_a_heading_too_long_for_the_frame_raises():
    with pytest.raises(MissingDataError, match="will not fit"):
        parse_spec(json.dumps([entry(heading="one two three four five")]), ["one."])


def test_too_many_checklist_items_raises():
    items = [f"item {n}" for n in range(MAX_CHECKLIST_ITEMS + 1)]
    with pytest.raises(MissingDataError, match="glance-able"):
        parse_spec(json.dumps([entry(checklist=items)]), ["one."])


def test_empty_checklist_strings_are_dropped():
    specs = parse_spec(json.dumps([entry(checklist=["real", "  ", ""])]), ["one."])
    assert specs[0].checklist == ("REAL",)


def test_a_beat_with_no_lettering_is_marked_as_such():
    assert not parse_spec(json.dumps([entry()]), ["one."])[0].has_lettering
    assert parse_spec(json.dumps([entry(heading="risk")]), ["one."])[0].has_lettering


def test_no_beats_raises():
    with pytest.raises(MissingDataError):
        parse_spec("[]", [])


# --- lettering layout -------------------------------------------------------

def test_each_heading_word_gets_its_own_line():
    # The reference stacks "LEGAL" over "REQUIREMENT" rather than running them
    # across a 1920px frame.
    lines = caption_lines(BeatSpec("t", "s", heading="LEGAL REQUIREMENT"))
    assert [text for text, _, _ in lines] == ["LEGAL", "REQUIREMENT"]
    assert all(kind == "heading" for _, _, kind in lines)


def test_checklist_items_carry_the_tick_marker():
    lines = caption_lines(BeatSpec("t", "s", checklist=("AIR INTAKE",)))
    assert lines[0][0].startswith("[x]")
    assert lines[0][2] == "body"


def test_a_beat_with_no_lettering_produces_no_lines():
    assert caption_lines(BeatSpec("t", "s")) == []


# --- generation -------------------------------------------------------------

def test_generation_asks_for_one_entry_per_beat():
    asked = {}

    class FakeClient:
        def complete(self, system, user, max_tokens=0):
            asked["user"] = user
            return json.dumps([entry(), entry("a hinge")])

    specs = generate_spec(FakeClient(), ["one.", "two."])
    assert len(specs) == 2
    assert "exactly 2 JSON objects" in asked["user"]


# --- junk filtering ---------------------------------------------------------

def test_punctuation_only_checklist_items_are_dropped():
    # gemma4 returned the literal string "[]" as a checklist item, which would
    # have been drawn on the frame as a ticked line reading "[]".
    specs = parse_spec(
        json.dumps([entry(checklist=["[]", "-", "REAL ITEM", "..."])]), ["one."]
    )
    assert specs[0].checklist == ("REAL ITEM",)


def test_a_beat_whose_only_checklist_item_was_junk_has_no_lettering():
    specs = parse_spec(json.dumps([entry(checklist=["[]"])]), ["one."])
    assert not specs[0].has_lettering


# --- chunking ---------------------------------------------------------------

def test_a_long_script_is_planned_in_chunks():
    # One call for 200 beats overruns both the token budget and any sane HTTP
    # timeout, and one malformed response would cost the whole script.
    sizes = []

    class FakeClient:
        def complete(self, system, user, max_tokens=0):
            count = int(user.split()[0])
            sizes.append(count)
            return json.dumps([entry(f"subject {n}") for n in range(count)])

    beats = [f"Sentence number {n} goes here." for n in range(45)]
    specs = generate_spec(FakeClient(), beats, chunk=20)
    assert len(specs) == 45
    assert sizes == [20, 20, 5]


def test_each_chunk_is_told_where_it_sits_in_the_script():
    seen = []

    class FakeClient:
        def complete(self, system, user, max_tokens=0):
            seen.append(user)
            count = int(user.split()[0])
            return json.dumps([entry() for _ in range(count)])

    generate_spec(FakeClient(), [f"Beat {n} here." for n in range(30)], chunk=20)
    assert "beats 1-20 of 30" in seen[0]
    assert "beats 21-30 of 30" in seen[1]


def test_chunked_specs_stay_paired_with_their_own_beats():
    class FakeClient:
        def complete(self, system, user, max_tokens=0):
            count = int(user.split()[0])
            return json.dumps([entry() for _ in range(count)])

    beats = [f"Beat {n} here." for n in range(25)]
    specs = generate_spec(FakeClient(), beats, chunk=20)
    assert [s.text for s in specs] == beats


# --- resilience -------------------------------------------------------------

def test_a_chunk_is_retried_when_the_model_breaks_a_stated_constraint():
    # auto/best-free returned the heading "EMPTY ROOM, WASTED MONEY" and a
    # three-word cap failed the whole 20-beat chunk over that one entry.
    calls = []

    class FlakyClient:
        def complete(self, system, user, max_tokens=0):
            calls.append(1)
            if len(calls) == 1:
                return json.dumps([entry(heading="one two three four five")])
            return json.dumps([entry(heading="fine")])

    specs = generate_spec(FlakyClient(), ["one."])
    assert specs[0].heading == "FINE"
    assert len(calls) == 2


def test_a_chunk_that_keeps_failing_reports_what_was_wrong():
    class BrokenClient:
        def complete(self, system, user, max_tokens=0):
            return json.dumps([entry(heading="one two three four five")])

    with pytest.raises(MissingDataError, match="will not fit"):
        generate_spec(BrokenClient(), ["one."])


def test_a_four_word_heading_is_accepted():
    specs = parse_spec(json.dumps([entry(heading="empty room, wasted money")]), ["one."])
    assert specs[0].heading == "EMPTY ROOM, WASTED MONEY"


# --- chapters ---------------------------------------------------------------

def test_chapters_are_parsed():
    e = entry(); e["chapter"] = 2
    assert parse_spec(json.dumps([e]), ["one."])[0].chapter == 2


def test_chapters_never_go_backwards():
    # A model that renumbers 3 then 2 would flash an earlier marker onto a later
    # beat; each beat inherits the highest chapter seen so far.
    a = entry("a"); a["chapter"] = 3
    b = entry("b"); b["chapter"] = 2
    specs = parse_spec(json.dumps([a, b]), ["one.", "two."])
    assert [s.chapter for s in specs] == [3, 3]


def test_a_missing_or_zero_chapter_means_no_marker():
    assert parse_spec(json.dumps([entry()]), ["one."])[0].chapter == 0
