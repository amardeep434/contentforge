"""Lettering. It is the content, not decoration, so it must be exact and placed."""

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from contentforge.errors import MissingDataError
from contentforge.visuals.caption import (
    TextBlock,
    apply,
    checklist,
    find_clear_region,
    measure,
    place_blocks,
)


def frame(tmp_path, busy_side="right"):
    """A frame with linework on one half and empty ground on the other."""
    im = Image.new("RGB", (1920, 1080), (245, 241, 232))
    d = ImageDraw.Draw(im)
    x0 = 1000 if busy_side == "right" else 0
    for i in range(0, 900, 12):                    # dense hatching = "drawing"
        d.line([x0 + i % 900, 100, x0 + i % 900, 980], fill=(20, 20, 20), width=3)
    p = tmp_path / f"{busy_side}.png"
    im.save(p)
    return p


def test_text_lands_on_the_empty_half(tmp_path):
    # The failure this exists to prevent: a caption drawn across the drawing.
    image = Image.open(frame(tmp_path, busy_side="right"))
    x, y = find_clear_region(image, 600, 300)
    assert x < 900, "text was placed over the busy side"


def test_it_finds_the_other_side_too(tmp_path):
    image = Image.open(frame(tmp_path, busy_side="left"))
    x, _ = find_clear_region(image, 500, 250)
    assert x > 700


def test_a_full_frame_still_returns_the_quietest_area(tmp_path):
    # Better to place text somewhere defensible than to fail the render.
    im = Image.new("RGB", (1920, 1080))
    d = ImageDraw.Draw(im)
    for i in range(0, 1920, 8):
        d.line([i, 0, i, 1080], fill=(0, 0, 0), width=3)
    p = tmp_path / "full.png"; im.save(p)
    x, y = find_clear_region(Image.open(p), 400, 200)
    assert 0 <= x < 1920 and 0 <= y < 1080


def test_blocks_stack_without_overlapping(tmp_path):
    blocks = place_blocks(frame(tmp_path), [
        ("LEGAL", 92, "heading"), ("REQUIREMENT", 92, "heading"),
        ("adequate ventilation", 38, "body"),
    ])
    ys = [b.y for b in blocks]
    assert ys == sorted(ys) and len(set(ys)) == 3


def test_all_blocks_share_a_left_margin(tmp_path):
    blocks = place_blocks(frame(tmp_path), [("A", 60, "heading"), ("B", 60, "heading")])
    assert len({b.x for b in blocks}) == 1


def test_a_checklist_marks_every_item():
    blocks = checklist(["one", "two", "three"], 100, 200)
    assert len(blocks) == 3
    assert all(b.text.startswith("[x]") for b in blocks)
    assert blocks[0].text.endswith("ONE")          # upper-cased like the reference


def test_text_off_the_frame_raises(tmp_path):
    p = frame(tmp_path)
    with pytest.raises(MissingDataError, match="outside"):
        apply(p, [TextBlock("x", 5000, 20)], tmp_path / "o.png")


def test_an_empty_block_raises(tmp_path):
    p = frame(tmp_path)
    with pytest.raises(MissingDataError):
        apply(p, [TextBlock("   ", 10, 10)], tmp_path / "o.png")


def test_no_blocks_raises(tmp_path):
    with pytest.raises(MissingDataError, match="carries no argument"):
        apply(frame(tmp_path), [], tmp_path / "o.png")


def test_output_keeps_the_frame_size(tmp_path):
    out = apply(frame(tmp_path), [TextBlock("HELLO", 100, 100)], tmp_path / "o.png")
    assert Image.open(out).size == (1920, 1080)


def test_measure_grows_with_size():
    small = measure("LEGAL REQUIREMENT", "heading", 30)[0]
    large = measure("LEGAL REQUIREMENT", "heading", 90)[0]
    assert large > small * 2


def test_stacked_lines_never_overlap(tmp_path):
    # The bug this exists to prevent: "REQUIREMENT" at 92px measured 74px of ink
    # but occupies 133px of line, so the heading was drawn into the checklist
    # beneath it - 59px of overlap per line.
    from contentforge.visuals.caption import line_height

    lines = [("LEGAL", 92, "heading"), ("REQUIREMENT", 92, "heading"),
             ("[x]  ADEQUATE VENTILATION", 38, "body"),
             ("[x]  AIR CIRCULATION", 38, "body")]
    blocks = place_blocks(frame(tmp_path), lines)
    for current, following in zip(blocks, blocks[1:]):
        bottom = current.y + line_height(current.font, current.size)
        assert following.y >= bottom, (
            f"{following.text!r} starts at {following.y} but {current.text!r} "
            f"runs to {bottom}"
        )


def test_line_height_exceeds_ink_extent():
    # Ink extent omits ascent and descent; using it for layout is the bug.
    from contentforge.visuals.caption import line_height

    assert line_height("heading", 92) > measure("REQUIREMENT", "heading", 92)[1]


def test_a_checklist_spaces_itself_from_the_font(tmp_path):
    from contentforge.visuals.caption import line_height

    blocks = checklist(["one", "two"], 100, 200, size=38)
    assert blocks[1].y - blocks[0].y >= line_height("body", 38)


def test_a_centered_heading_sits_near_the_top_and_is_centred():
    from contentforge.visuals.caption import centered_heading, measure
    blocks = centered_heading((1920, 1080), [("TRUTH", 120, "heading")])
    b = blocks[0]
    assert b.y < 1080 * 0.2                         # near the top
    text_w = measure("TRUTH", "heading", 120)[0]
    assert abs((b.x + text_w / 2) - 960) < 5        # horizontally centred


def test_chapter_numbers_are_spelled_not_numbered():
    from contentforge.visuals.caption import ordinal_word
    assert ordinal_word(2) == "TWO"
    assert ordinal_word(0) == "ZERO"
    assert ordinal_word(99) == "99"          # beyond the table, digits


def test_a_negative_chapter_raises():
    from contentforge.visuals.caption import ordinal_word
    import pytest
    from contentforge.errors import MissingDataError
    with pytest.raises(MissingDataError):
        ordinal_word(-1)


def test_the_chapter_label_is_in_the_accent_colour_top_left():
    from contentforge.visuals.caption import ACCENT, INK, chapter_label
    block = chapter_label((1920, 1080), 3)
    assert block.text == "THREE"
    assert block.colour == ACCENT
    assert block.colour != INK
    assert block.x < 1920 * 0.2 and block.y < 1080 * 0.2
