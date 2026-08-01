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
