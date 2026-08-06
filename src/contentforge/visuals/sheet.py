"""Draw the sheet of paper the lettering sits on.

The reference channel does not float text over the background. It draws a
document - a pale sheet with an ink border, standing on the table - and puts the
heading, the checklist, a stamp and a signature inside it. That is most of why
their frame reads as composed and ours read as a caption laid over a picture.

The sheet is drawn here rather than generated for the same reason the lettering
is: diffusion cannot be relied on to produce a rectangle with room for four
lines of text in a known place. Drawn, its position is known exactly, so the
lettering can be placed inside it without measuring anything and without hoping
the frame happened to have empty space in a usable shape.

Everything is derived from the text that has to fit. A sheet sized to the frame
and text fitted into it afterwards is how you get four words in a sheet built
for twelve.
"""

from dataclasses import dataclass
from pathlib import Path

from contentforge.errors import MissingDataError
from contentforge.visuals.caption import INK, PAPER, line_height, measure

#: Breathing room inside the sheet, all four sides. The reference keeps a
#: generous margin; it is part of why the document reads as a document.
PADDING = 54

#: Ink weight of the sheet's edge, at 1080p.
BORDER = 5

#: Offset of the shadow that lifts the sheet off the background.
SHADOW = 7

#: Slight lean, as if the sheet were propped rather than pasted. The reference
#: tilts by a couple of degrees; dead-straight reads as a slide.
TILT_DEGREES = 1.5

#: The sheet never covers more than this share of the frame width.
MAX_WIDTH_SHARE = 0.46


@dataclass(frozen=True)
class Sheet:
    """Where the sheet was drawn, so lettering can be placed inside it."""

    left: int
    top: int
    width: int
    height: int

    @property
    def text_left(self) -> int:
        return self.left + PADDING

    @property
    def text_top(self) -> int:
        return self.top + PADDING


#: Reserved strip along the bottom of the sheet for the stamp and signature.
#: Without it they are drawn over the last checklist row, which is exactly the
#: overlap the lettering fix removed further up.
FOOTER = 92


def size_for(lines: list[tuple[str, int, str]], line_gap: int = 0,
             footer: bool = False) -> tuple[int, int]:
    """The smallest sheet that holds these lines with a margin."""
    if not lines:
        raise MissingDataError("a sheet with no lettering on it is just a rectangle")
    widths, height = [], 0
    for text, size, kind in lines:
        widths.append(measure(text.replace("[x]", "X"), kind, size)[0])
        height += line_height(kind, size) + line_gap
    return (
        max(widths) + PADDING * 2,
        height + PADDING * 2 + (FOOTER if footer else 0),
    )


def quieter_side(image, margin: float = 0.45) -> str:
    """Which half of the frame has less drawing in it.

    The sheet has to go where the illustration is not. Choosing a fixed side
    puts a document over the subject the moment the model composes the other
    way round, and it composes whichever way it likes.
    """
    from contentforge.visuals.caption import busyness_map

    scores = busyness_map(image)
    columns = len(scores[0])
    edge = max(1, int(columns * margin))
    left = sum(sum(row[:edge]) for row in scores)
    right = sum(sum(row[-edge:]) for row in scores)
    return "left" if left <= right else "right"


def place(frame_size: tuple[int, int], sheet_size: tuple[int, int],
          side: str = "left") -> Sheet:
    """Sit the sheet on one side of the frame, vertically centred.

    Left by default: the reference puts the document left and the object it
    describes right, so the eye reads the claim before the illustration of it.
    """
    frame_w, frame_h = frame_size
    width, height = sheet_size
    limit = int(frame_w * MAX_WIDTH_SHARE)
    if width > limit:
        raise MissingDataError(
            f"the lettering needs a {width}px sheet but only {limit}px is "
            "available; shorten the heading or the checklist"
        )
    if height > frame_h - PADDING * 2:
        raise MissingDataError(
            f"the lettering needs a {height}px sheet, taller than the frame"
        )
    margin = frame_w // 22
    left = frame_w - width - margin if side == "right" else margin
    return Sheet(left=left, top=(frame_h - height) // 2, width=width, height=height)


def draw(image_path: Path, sheet: Sheet, out_path: Path | None = None,
         stamp: str = "", signature: bool = False) -> Path:
    """Composite the sheet onto a frame, ready to be lettered.

    Drawn on its own layer and rotated before compositing, so the tilt applies
    to the sheet and not to the illustration under it.
    """
    from PIL import Image, ImageDraw

    if not image_path.exists():
        raise MissingDataError(f"no frame to draw a sheet on at {image_path}")
    frame = Image.open(image_path).convert("RGBA")

    pad = SHADOW * 4
    layer = Image.new("RGBA", (sheet.width + pad, sheet.height + pad), (0, 0, 0, 0))
    pen = ImageDraw.Draw(layer)
    box = [pad // 2, pad // 2, pad // 2 + sheet.width, pad // 2 + sheet.height]

    pen.rectangle([c + SHADOW for c in box], fill=(*INK, 46))
    pen.rectangle(box, fill=(*PAPER, 255), outline=(*INK, 255), width=BORDER)

    if stamp:
        _stamp(pen, box, stamp)
    if signature:
        _signature(pen, box)

    layer = layer.rotate(TILT_DEGREES, resample=Image.BICUBIC, expand=False)
    frame.alpha_composite(layer, (sheet.left - pad // 2, sheet.top - pad // 2))
    target = out_path or image_path
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.convert("RGB").save(target)
    return target


def _stamp(pen, box, text: str) -> None:
    """The bordered mark the reference puts in the sheet's bottom left."""
    from contentforge.visuals.caption import load_font

    size = 22
    font = load_font("body", size)
    width = pen.textlength(text.upper(), font=font)
    left, bottom = box[0] + PADDING, box[3] - PADDING // 2
    pen.rectangle(
        [left, bottom - size * 2, left + width + 22, bottom],
        outline=(*INK, 190), width=3,
    )
    pen.text((left + 11, bottom - size * 1.7), text.upper(), font=font,
             fill=(*INK, 190))


def _signature(pen, box) -> None:
    """A scribble, not a name. The reference's signature is illegible by design.

    Drawn from a fixed curve rather than a random one so a rerun of the same
    video produces the same frame.
    """
    right, bottom = box[2] - PADDING, box[3] - PADDING
    span = min(150, (box[2] - box[0]) // 3)
    points = [
        (right - span, bottom),
        (right - span * 0.78, bottom - 26),
        (right - span * 0.60, bottom - 4),
        (right - span * 0.44, bottom - 30),
        (right - span * 0.24, bottom - 8),
        (right - span * 0.08, bottom - 22),
        (right, bottom - 12),
    ]
    pen.line(points, fill=(*INK, 210), width=4, joint="curve")
