"""Draw the words onto the picture.

This is not decoration. Put the reference channel's frame beside a generated one
and the difference is not resolution — it is that theirs contains "LEGAL
REQUIREMENT", four checklist lines, a stamp and a signature, all perfectly
legible, and the drawing exists to serve them. The illustration is the setting;
the lettering is the argument.

No diffusion model renders text this cleanly, which is why "text, letters, words"
sits in the negative prompt and everything readable is composited here instead,
where it is exact.

Fonts are hand-lettered so the type belongs to the drawing rather than sitting on
top of it. Permanent Marker for headings (bold marker caps, matching the
reference), Patrick Hand for list items and labels.
"""

from dataclasses import dataclass
from pathlib import Path

from contentforge.errors import MissingDataError

FONT_DIR = Path.home() / ".local/share/fonts/contentforge"
HEADING_FONT = FONT_DIR / "permanentmarker.ttf"
BODY_FONT = FONT_DIR / "patrickhand.ttf"

#: Sampled from the reference frame rather than guessed.
INK = (26, 26, 26)
PAPER = (245, 241, 232)

#: Nothing sits closer to the edge than this. The reference keeps generous
#: margins, which is part of why it reads as uncluttered.
MARGIN = 90


@dataclass(frozen=True)
class TextBlock:
    """One run of lettering placed on the frame."""

    text: str
    x: int
    y: int
    size: int = 64
    font: str = "heading"
    colour: tuple = INK


def load_font(kind: str, size: int):
    from PIL import ImageFont

    path = HEADING_FONT if kind == "heading" else BODY_FONT
    if not path.exists():
        raise MissingDataError(
            f"font missing at {path}. See docs/setup/local-image-generation.md - "
            "captions are the content, not an optional flourish"
        )
    return ImageFont.truetype(str(path), size)


def checklist(items: list[str], x: int, y: int, size: int = 34,
              spacing: int = 0) -> list[TextBlock]:
    """A ticked list, as the reference uses for its checklists.

    The tick is drawn as a glyph rather than an image so it inherits the ink
    colour and never mismatches the lettering.
    """
    step = spacing or (line_height("body", size) + 14)
    blocks = []
    for index, item in enumerate(items):
        blocks.append(TextBlock(f"[x]  {item.upper()}", x, y + index * step,
                                size=size, font="body"))
    return blocks


def apply(image_path: Path, blocks: list[TextBlock], out_path: Path) -> Path:
    """Composite lettering onto a generated illustration."""
    from PIL import Image, ImageDraw

    if not blocks:
        raise MissingDataError(
            "no text blocks; a frame with no lettering carries no argument"
        )
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    width, height = image.size

    for block in blocks:
        if not block.text.strip():
            raise MissingDataError("an empty text block was queued for drawing")
        if not (0 <= block.x <= width and 0 <= block.y <= height):
            raise MissingDataError(
                f"text block at ({block.x}, {block.y}) falls outside the "
                f"{width}x{height} frame and would not be visible"
            )
        font = load_font(block.font, block.size)
        text = block.text
        # Checkbox glyph: drawn, not typed, so it matches the ink weight.
        if text.startswith("[x]"):
            box = block.size
            top = block.y + int(box * 0.12)
            draw.rectangle(
                [block.x, top, block.x + box, top + box],
                outline=block.colour, width=max(3, box // 14),
            )
            draw.line([block.x + box * 0.2, top + box * 0.55,
                       block.x + box * 0.42, top + box * 0.78],
                      fill=block.colour, width=max(4, box // 10))
            draw.line([block.x + box * 0.42, top + box * 0.78,
                       block.x + box * 0.84, top + box * 0.2],
                      fill=block.colour, width=max(4, box // 10))
            text = text[3:].lstrip()
            draw.text((block.x + box * 1.6, block.y), text, font=font,
                      fill=block.colour)
            continue
        draw.text((block.x, block.y), text, font=font, fill=block.colour)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)
    return out_path


def busyness_map(image, grid: int = 24):
    """How much ink sits in each cell of a grid over the image.

    Text must not land on the drawing. With 200 frames per video nobody is
    placing it by hand, so the frame is measured instead: high local variance
    means linework, near-zero means empty ground.
    """
    from PIL import ImageFilter

    grey = image.convert("L").filter(ImageFilter.FIND_EDGES)
    width, height = grey.size
    cell_w, cell_h = width // grid, height // grid
    scores = []
    for row in range(grid):
        line = []
        for col in range(grid):
            box = (col * cell_w, row * cell_h, (col + 1) * cell_w, (row + 1) * cell_h)
            patch = grey.crop(box)
            line.append(sum(patch.getdata()) / max(patch.width * patch.height, 1))
        scores.append(line)
    return scores


def find_clear_region(image, want_w: int, want_h: int, grid: int = 24,
                      threshold: float = 6.0) -> tuple[int, int]:
    """Top-left corner of an empty area big enough for a block of text.

    Scans left-to-right, top-to-bottom and takes the first region whose every
    cell is below the ink threshold, preferring the upper left because that is
    where the reference channel puts its headings.
    """
    width, height = image.size
    scores = busyness_map(image, grid)
    cell_w, cell_h = width // grid, height // grid
    need_cols = max(1, -(-want_w // cell_w))
    need_rows = max(1, -(-want_h // cell_h))

    best = None
    for row in range(grid - need_rows + 1):
        for col in range(grid - need_cols + 1):
            block = [scores[r][c]
                     for r in range(row, row + need_rows)
                     for c in range(col, col + need_cols)]
            if max(block) <= threshold:
                return col * cell_w + MARGIN // 2, row * cell_h + MARGIN // 2
            quiet = sum(block) / len(block)
            if best is None or quiet < best[0]:
                best = (quiet, col * cell_w + MARGIN // 2, row * cell_h + MARGIN // 2)
    if best is None:
        raise MissingDataError("could not measure the frame for text placement")
    # Nothing was fully clear; use the quietest area rather than overlapping the
    # busiest, and let the caller decide whether that is good enough.
    return best[1], best[2]


def line_height(kind: str, size: int) -> int:
    """Vertical space one line actually occupies.

    NOT the ink extent. `textbbox` measures the drawn glyphs, so "REQUIREMENT"
    at 92px reports about cap height and omits ascent and descent entirely -
    59px short per line, which stacked the heading straight into the checklist
    beneath it. The font's own metrics are the truth.
    """
    ascent, descent = load_font(kind, size).getmetrics()
    return ascent + descent


def stack_blocks(lines: list[tuple[str, int, str]], x: int, y: int,
                 line_gap: int = 0) -> list[TextBlock]:
    """Stack lines downward from a known corner.

    Separate from `place_blocks` because when the lettering sits on a drawn
    sheet the position is already decided - measuring the frame for empty space
    would be looking for somewhere the sheet is not.
    """
    blocks, cursor = [], y
    for text, size, kind in lines:
        blocks.append(TextBlock(text, x, cursor, size=size, font=kind))
        cursor += line_height(kind, size) + line_gap
    return blocks


def place_blocks(image_path: Path, lines: list[tuple[str, int, str]],
                 line_gap: int = 0) -> list[TextBlock]:
    """Lay out a stack of lines in whatever empty space the frame has.

    The fallback for a frame with no sheet on it. Where there is a sheet, use
    `stack_blocks` against its known corner instead.
    """
    from PIL import Image

    image = Image.open(image_path)
    widths, heights = [], []
    for text, size, kind in lines:
        widths.append(measure(text.replace("[x]", "X"), kind, size)[0])
        heights.append(line_height(kind, size) + line_gap)
    x, y = find_clear_region(image, max(widths), sum(heights))
    return stack_blocks(lines, x, y, line_gap)


def measure(text: str, kind: str, size: int) -> tuple[int, int]:
    """Rendered size, so a caller can lay out without guessing."""
    from PIL import Image, ImageDraw

    font = load_font(kind, size)
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right - left, bottom - top


def fits(text: str, kind: str, size: int, max_width: int) -> bool:
    return measure(text, kind, size)[0] <= max_width
