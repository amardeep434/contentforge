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
        parse_spec(json.dumps([entry(heading="one two three four")]), ["one."])


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
