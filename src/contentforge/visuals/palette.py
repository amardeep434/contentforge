"""Pull a generated frame onto the reference channel's palette.

Measured against a native 1920x1080 frame from the reference channel and a
generated one, downsampled to 320x180 so a few thousand outlier pixels cannot
move the figure:

                       background        median saturation   mean brightness
    reference          rgb(240,232,216)  0.079               0.839
    generated          rgb(232,208,160)  0.315               0.845

Brightness already matches. The whole visible difference is chroma - ours is
four times as saturated, which is why a cream wall reads as tan and a grey fan
reads as orange.

**Prompting does not fix this.** The house style already says "flat plain cream
off-white background, muted colours" and sd-turbo produces the frame above
anyway. So the correction is measured per image and applied after generation,
where it is arithmetic rather than persuasion.

Scaling is adaptive rather than a fixed factor: each frame is measured and
scaled to hit the reference median. A fixed factor tuned on one image drifts as
soon as a beat is mostly sky or mostly skin, and would have to be re-tuned for
every model.
"""

from dataclasses import dataclass
from pathlib import Path

from contentforge.errors import MissingDataError

#: Median HSV saturation of the reference frame, at 320x180.
TARGET_SATURATION = 0.079

#: 90th percentile of the same frame. Both anchors are needed, and this is the
#: one a first attempt got wrong: scaling everything by a single factor to hit
#: the median took our p90 from 0.402 down to 0.097 against the reference's
#: 0.337, so the wood and the metal went pale along with the background.
#:
#: The reference distribution is two things at once - a near-neutral flat
#: background and objects that are properly coloured. A single multiplier
#: cannot produce that shape from a frame where everything is uniformly tan;
#: matching at two points can approximate it.
TARGET_P90 = 0.337

#: Ceiling on the gain of the two-point fit. Stretching chroma amplifies
#: whatever compression noise the upscaler left behind, and past this the
#: background starts to mottle.
MAX_GAIN = 2.4

#: Nothing ends up more saturated than the most saturated thing in the
#: reference frame.
MAX_SATURATION = 0.40

#: The reference frame's own background, sampled from it. The background is the
#: one colour in a frame that can be matched exactly instead of approached, and
#: holding it constant across 200 shots is most of what makes a video look like
#: one hand drew it.
REFERENCE_BACKGROUND = (240, 232, 216)

#: How far a pixel can sit from the modal background colour and still count as
#: background rather than drawing. Wide enough to swallow sd-turbo's paper
#: grain, far narrower than the gap to any inked line.
TEXTURE_TOLERANCE = 20

#: Below this the image is effectively greyscale and scaling it is noise
#: amplification.
MIN_MEASURABLE_SATURATION = 0.01

#: Sampled size for measurement. Large enough to be stable, small enough that
#: measuring 200 frames costs nothing.
SAMPLE = (320, 180)


@dataclass(frozen=True)
class Reading:
    """What a frame actually looks like, before anything is done to it."""

    background: tuple[int, int, int]
    median_saturation: float
    p90_saturation: float
    mean_brightness: float

    @property
    def is_on_palette(self) -> bool:
        return self.median_saturation <= TARGET_SATURATION * 1.25


def measure(image) -> Reading:
    """Background colour and chroma of a frame.

    The background is taken as the modal colour in 8-level bins: on this style
    it is by far the largest flat area, and a mode survives the linework that
    would drag a mean around.
    """
    import collections

    if not all(image.size):
        raise MissingDataError("cannot measure an image with no pixels in it")
    pixels = list(image.convert("RGB").resize(SAMPLE).getdata())

    bins = collections.Counter(
        (r // 8 * 8, g // 8 * 8, b // 8 * 8) for r, g, b in pixels
    )
    background = bins.most_common(1)[0][0]

    saturations, values = [], []
    for red, green, blue in pixels:
        high, low = max(red, green, blue), min(red, green, blue)
        saturations.append(0.0 if high == 0 else (high - low) / high)
        values.append(high / 255)
    saturations.sort()

    return Reading(
        background=background,
        median_saturation=saturations[len(saturations) // 2],
        p90_saturation=saturations[int(len(saturations) * 0.9)],
        mean_brightness=sum(values) / len(values),
    )


def flatten_background(image, reading: Reading, tolerance: int = TEXTURE_TOLERANCE,
                       fill: tuple[int, int, int] | None = None):
    """Replace the mottled background with one flat colour.

    The reference channel's background is flat. sd-turbo's is not - it carries a
    paper-grain texture that the house style's "no texture" and the negative
    prompt's "grain, noise" both ask for and neither gets. Left in, the chroma
    stretch below multiplies it into visible blotches.

    Everything within `tolerance` of the modal colour becomes exactly the modal
    colour. Safe on this style specifically because the prompt forbids gradients
    and shading, so there is nothing near the background that is meant to be a
    smooth ramp - only linework, which is far outside the tolerance.
    """
    from PIL import Image, ImageChops

    found = Image.new("RGB", image.size, reading.background)
    distance = ImageChops.difference(image, found).convert("L")
    mask = distance.point(lambda level: 255 if level <= tolerance else 0)
    return Image.composite(Image.new("RGB", image.size, fill or reading.background),
                           image, mask)


def fit(reading: Reading, median: float = TARGET_SATURATION,
        p90: float = TARGET_P90) -> tuple[float, float]:
    """Gain and offset mapping this frame's chroma onto the reference's.

    Two anchors, so the flat background lands near-neutral while whatever was
    genuinely coloured stays coloured. Returns the identity when the frame is
    already flat enough to measure nothing useful, or when the fit would need
    more gain than is safe.
    """
    spread = reading.p90_saturation - reading.median_saturation
    if reading.median_saturation < MIN_MEASURABLE_SATURATION or spread <= 0:
        return 1.0, 0.0
    gain = (p90 - median) / spread
    if gain <= 0:
        return 1.0, 0.0
    gain = min(gain, MAX_GAIN)
    return gain, median - gain * reading.median_saturation


def normalise(source: Path, destination: Path | None = None,
              median: float = TARGET_SATURATION,
              p90: float = TARGET_P90) -> Reading:
    """Rewrite a frame at the reference channel's chroma.

    Saturation only. Hue is left alone because the reference is not neutral -
    it is a warm cream - and rotating hue would fight the style rather than
    match it. Brightness is left alone because it already matches: measured
    0.839 against 0.845, which is the whole reason this stage touches chroma
    and nothing else.
    """
    from PIL import Image

    if not source.exists():
        raise MissingDataError(f"no image to normalise at {source}")
    image = Image.open(source).convert("RGB")
    before = measure(image)
    # Flatten first. Stretching chroma over a textured background amplifies the
    # texture into blotches, which is worse than the tint it was fixing.
    image = flatten_background(image, before)
    gain, offset = fit(before, median, p90)

    if (gain, offset) != (1.0, 0.0):
        ceiling = int(MAX_SATURATION * 255)
        table = [
            max(0, min(ceiling, int((level / 255 * gain + offset) * 255)))
            for level in range(256)
        ]
        hue, saturation, value = image.convert("HSV").split()
        image = Image.merge(
            "HSV", (hue, saturation.point(table), value)
        ).convert("RGB")

    # Snap to the reference's own background last. The stretch moves whatever
    # the first flatten settled on, and the background is the one colour in the
    # frame that can be matched exactly rather than approached.
    image = flatten_background(image, measure(image), fill=REFERENCE_BACKGROUND)

    out_path = destination or source
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)
    return measure(image)
