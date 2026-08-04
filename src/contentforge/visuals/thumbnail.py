"""Build the 1280x720 thumbnail from a frame the video already contains.

Not a separate illustration. The thumbnail is a hero frame from the video with
a few huge words over it, which is what the reference channel does and what
keeps the thumbnail honest - it shows something that is actually in the video.

The headline is set in Bangers, the one display face among the installed fonts,
with a heavy outline so it stays legible over any part of the picture. A
thumbnail whose text vanishes into the drawing behind it is the failure this
guards against, so the stroke is not optional.

The earlier thumbnail module was built on a refuted premise (that polishing the
asset drives views, C-011) and generated a bespoke image. This one reuses a
real frame and only sets type, which is both simpler and truthful.
"""

from pathlib import Path

from contentforge.errors import MissingDataError
from contentforge.visuals.caption import FONT_DIR, INK

WIDTH, HEIGHT = 1280, 720

DISPLAY_FONT = FONT_DIR / "bangers.ttf"

#: The headline never exceeds this share of the frame width, so it always has a
#: margin and never reaches the edge.
MAX_TEXT_WIDTH = 0.88

#: Words beyond this stop being readable at a glance in a thumbnail grid.
MAX_WORDS = 5

#: Cream fill, dark outline - the reverse of the captions, because a thumbnail
#: headline reads better light-on-dark at small sizes in the sidebar.
FILL = (248, 244, 236)
OUTLINE = INK


def _load(size: int):
    from PIL import ImageFont

    if not DISPLAY_FONT.exists():
        raise MissingDataError(
            f"thumbnail font missing at {DISPLAY_FONT}. See "
            "docs/setup/local-image-generation.md"
        )
    return ImageFont.truetype(str(DISPLAY_FONT), size)


def _fit_font_size(draw, text: str, max_width: int, start: int = 200) -> int:
    """Largest size at which the headline fits the frame width."""
    size = start
    while size > 24:
        font = _load(size)
        left, _, right, _ = draw.textbbox((0, 0), text, font=font, stroke_width=size // 12)
        if right - left <= max_width:
            return size
        size -= 6
    return 24


def _wrap(headline: str) -> str:
    """Two lines when the headline is more than three words, else one."""
    words = headline.split()
    if len(words) <= 3:
        return headline
    mid = (len(words) + 1) // 2
    return "\n".join([" ".join(words[:mid]), " ".join(words[mid:])])


def compose(hero: Path, headline: str, out_path: Path,
            position: str = "bottom") -> Path:
    """A frame from the video, filled to 1280x720, with the headline over it."""
    from PIL import Image, ImageDraw

    if not hero.exists():
        raise MissingDataError(f"no hero frame for the thumbnail at {hero}")
    words = headline.split()
    if not words:
        raise MissingDataError("a thumbnail needs a headline")
    if len(words) > MAX_WORDS:
        raise MissingDataError(
            f"thumbnail headline is {len(words)} words; more than {MAX_WORDS} "
            "cannot be read at a glance"
        )

    image = _fill(Image.open(hero).convert("RGB"))
    draw = ImageDraw.Draw(image)
    text = _wrap(headline.upper())

    max_width = int(WIDTH * MAX_TEXT_WIDTH)
    widest = max(text.split("\n"), key=len)
    size = _fit_font_size(draw, widest, max_width)
    font = _load(size)
    stroke = max(3, size // 10)

    left, top, right, bottom = draw.multiline_textbbox(
        (0, 0), text, font=font, stroke_width=stroke, align="center", spacing=size // 6
    )
    x = (WIDTH - (right - left)) // 2
    y = HEIGHT - (bottom - top) - 60 if position == "bottom" else 60

    draw.multiline_text(
        (x, y), text, font=font, fill=FILL, stroke_width=stroke,
        stroke_fill=OUTLINE, align="center", spacing=size // 6,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)
    return out_path


def _fill(image):
    """Cover 1280x720 completely, cropping overflow, never distorting."""
    from PIL import Image

    scale = max(WIDTH / image.width, HEIGHT / image.height)
    resized = image.resize(
        (round(image.width * scale), round(image.height * scale)), Image.LANCZOS
    )
    left = (resized.width - WIDTH) // 2
    top = (resized.height - HEIGHT) // 2
    return resized.crop((left, top, left + WIDTH, top + HEIGHT))
