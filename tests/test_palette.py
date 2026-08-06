"""Chroma correction, measured against the reference channel's own frame."""

import pytest
from PIL import Image

from contentforge.errors import MissingDataError
from contentforge.visuals.palette import (
    MAX_GAIN,
    REFERENCE_BACKGROUND,
    TARGET_P90,
    TARGET_SATURATION,
    Reading,
    fit,
    flatten_background,
    measure,
    normalise,
)


def frame(background=(232, 208, 160), patch=None, size=(320, 180)):
    """A flat background with an optional coloured block in the corner.

    The block covers a quarter of the frame so it lands above the 90th
    percentile - a smaller one would be invisible to the measurement the
    correction is fitted against.
    """
    image = Image.new("RGB", size, background)
    if patch:
        image.paste(Image.new("RGB", (160, 90), patch), (10, 10))
    return image


# --- measuring --------------------------------------------------------------

def test_the_background_is_read_as_the_modal_colour():
    reading = measure(frame(background=(232, 208, 160), patch=(20, 20, 20)))
    assert reading.background == (232, 208, 160)


def test_an_empty_image_cannot_be_measured():
    with pytest.raises(MissingDataError):
        measure(Image.new("RGB", (0, 0)))


# --- fitting ----------------------------------------------------------------

def test_the_fit_lands_on_both_reference_anchors():
    reading = Reading((0, 0, 0), median_saturation=0.315,
                      p90_saturation=0.402, mean_brightness=0.845)
    gain, offset = fit(reading)
    # Gain would be 2.97 here, above the cap, so only the shape is asserted.
    assert gain == MAX_GAIN
    assert pytest.approx(gain * 0.315 + offset, abs=1e-6) == TARGET_SATURATION


def test_a_gentle_fit_hits_the_p90_anchor_exactly():
    reading = Reading((0, 0, 0), median_saturation=0.20,
                      p90_saturation=0.45, mean_brightness=0.8)
    gain, offset = fit(reading)
    assert gain < MAX_GAIN
    assert pytest.approx(gain * 0.45 + offset, abs=1e-6) == TARGET_P90


def test_an_already_flat_frame_is_left_alone():
    # No spread to fit against; scaling it would amplify nothing but noise.
    reading = Reading((0, 0, 0), median_saturation=0.0,
                      p90_saturation=0.0, mean_brightness=0.9)
    assert fit(reading) == (1.0, 0.0)


# --- flattening -------------------------------------------------------------

def test_background_texture_is_replaced_with_one_flat_colour():
    # sd-turbo puts a paper grain on the background that the chroma stretch
    # would otherwise amplify into visible blotches.
    speckled = frame()
    speckled.putpixel((100, 100), (236, 212, 164))   # within tolerance
    reading = measure(speckled)
    flattened = flatten_background(speckled, reading)
    assert flattened.getpixel((100, 100)) == reading.background


def test_linework_survives_flattening():
    inked = frame(patch=(20, 20, 20))
    flattened = flatten_background(inked, measure(inked))
    assert flattened.getpixel((20, 20)) == (20, 20, 20)


def test_flattening_can_snap_to_a_named_colour():
    image = frame()
    flattened = flatten_background(image, measure(image), fill=REFERENCE_BACKGROUND)
    assert flattened.getpixel((300, 170)) == REFERENCE_BACKGROUND


# --- end to end -------------------------------------------------------------

def test_normalising_lands_the_background_on_the_reference_exactly(tmp_path):
    path = tmp_path / "shot.png"
    frame(patch=(180, 90, 30)).save(path)
    after = normalise(path)
    assert after.background == REFERENCE_BACKGROUND


def test_normalising_pulls_an_over_saturated_frame_down(tmp_path):
    path = tmp_path / "shot.png"
    frame(background=(232, 168, 80), patch=(200, 60, 20)).save(path)
    before = measure(Image.open(path))
    after = normalise(path)
    assert after.median_saturation < before.median_saturation


def test_colour_is_not_crushed_along_with_the_tint(tmp_path):
    # The bug this exists to prevent: scaling everything by one factor to hit
    # the median took p90 from 0.402 to 0.097 against the reference's 0.337,
    # so the wood went pale along with the background.
    path = tmp_path / "shot.png"
    frame(background=(232, 208, 160), patch=(200, 70, 20)).save(path)
    after = normalise(path)
    assert after.p90_saturation > after.median_saturation


def test_a_missing_frame_raises(tmp_path):
    with pytest.raises(MissingDataError, match="no image to normalise"):
        normalise(tmp_path / "nothing.png")
