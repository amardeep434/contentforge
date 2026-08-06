"""The drawn document the lettering sits on."""

import pytest
from PIL import Image

from contentforge.errors import MissingDataError
from contentforge.visuals.sheet import (
    FOOTER,
    MAX_WIDTH_SHARE,
    PADDING,
    Sheet,
    draw,
    place,
    quieter_side,
    size_for,
)

FRAME = (1920, 1080)
LINES = [("LEGAL", 64, "heading"), ("[x]  AIR INTAKE", 34, "body")]


def test_the_sheet_is_sized_to_the_lettering_plus_a_margin():
    width, height = size_for(LINES)
    assert width > PADDING * 2
    assert height > PADDING * 2


def test_a_stamp_reserves_a_footer_rather_than_overlapping_the_last_line():
    # Without the reserved strip the stamp and signature were drawn over the
    # final checklist row.
    plain = size_for(LINES)[1]
    assert size_for(LINES, footer=True)[1] == plain + FOOTER


def test_a_sheet_with_no_lettering_raises():
    with pytest.raises(MissingDataError, match="just a rectangle"):
        size_for([])


# --- placement --------------------------------------------------------------

def test_the_sheet_sits_inside_the_frame():
    area = place(FRAME, size_for(LINES))
    assert area.left >= 0
    assert area.top >= 0
    assert area.left + area.width <= FRAME[0]
    assert area.top + area.height <= FRAME[1]


def test_the_right_hand_placement_hugs_the_right_edge():
    left = place(FRAME, size_for(LINES), "left")
    right = place(FRAME, size_for(LINES), "right")
    assert right.left > left.left


def test_text_starts_inside_the_sheet_not_on_its_border():
    area = place(FRAME, size_for(LINES))
    assert area.text_left == area.left + PADDING
    assert area.text_top == area.top + PADDING


def test_lettering_too_wide_for_the_frame_raises():
    too_wide = (int(FRAME[0] * MAX_WIDTH_SHARE) + 1, 200)
    with pytest.raises(MissingDataError, match="shorten the heading"):
        place(FRAME, too_wide)


def test_lettering_taller_than_the_frame_raises():
    with pytest.raises(MissingDataError, match="taller than the frame"):
        place(FRAME, (400, FRAME[1]))


# --- choosing a side --------------------------------------------------------

def test_the_sheet_goes_where_the_drawing_is_not():
    # A fixed side puts a document over the subject the moment the model
    # composes the other way round.
    image = Image.new("RGB", FRAME, (240, 232, 216))
    image.paste(Image.new("RGB", (600, 600), (10, 10, 10)), (60, 200))
    assert quieter_side(image) == "right"

    other = Image.new("RGB", FRAME, (240, 232, 216))
    other.paste(Image.new("RGB", (600, 600), (10, 10, 10)), (1260, 200))
    assert quieter_side(other) == "left"


# --- drawing ----------------------------------------------------------------

def test_drawing_a_sheet_changes_the_frame(tmp_path):
    path = tmp_path / "frame.png"
    Image.new("RGB", FRAME, (240, 232, 216)).save(path)
    before = Image.open(path).getpixel((200, 540))

    area = place(FRAME, size_for(LINES), "left")
    draw(path, area, stamp="regulation compliant", signature=True)

    after = Image.open(path).getpixel((area.left + 4, area.top + 4))
    assert after != before


def test_drawing_on_a_missing_frame_raises(tmp_path):
    with pytest.raises(MissingDataError, match="no frame to draw"):
        draw(tmp_path / "nothing.png", Sheet(0, 0, 100, 100))
