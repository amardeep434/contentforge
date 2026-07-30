"""Wikimedia Commons sourcing.

Every test here comes from a real trap seen in live results: a CC-BY file in a
public-domain search, and a Manet portrait *of* Monet sitting in a category that
contains "Claude Monet".
"""

import json
from datetime import datetime, timezone

import pytest

from contentforge.errors import MissingDataError
from contentforge.sourcing.commons import (
    by_artist,
    is_free_license,
    parse_commons,
    search_commons,
    search_url,
)

NOW = datetime(2026, 7, 30, tzinfo=timezone.utc)


def page(license_id="pd", short="Public domain", categories=(), title="File:X.jpg"):
    return {
        "title": title,
        "categories": [{"title": f"Category:{c}"} for c in categories],
        "imageinfo": [
            {
                "url": "https://upload.wikimedia.org/full.jpg",
                "thumburl": "https://upload.wikimedia.org/thumb.jpg",
                "extmetadata": {
                    "License": {"value": license_id},
                    "LicenseShortName": {"value": short},
                    "ObjectName": {"value": "Woman with a Parasol"},
                    "Credit": {"value": "<span>Own work</span>"},
                    "DateTimeOriginal": {"value": "1875"},
                    # The photographer, not the painter — never used for
                    # authorship.
                    "Artist": {"value": "<a href='#'>Pierre André Leclercq</a>"},
                },
            }
        ],
    }


def body(*pages):
    return json.dumps({"query": {"pages": {str(i): p for i, p in enumerate(pages)}}})


# --- licence ----------------------------------------------------------------

def test_public_domain_and_cc0_are_accepted():
    assert is_free_license({"License": {"value": "pd"}})
    assert is_free_license({"License": {"value": "cc0"}})


def test_cc_by_is_rejected():
    # Seen live: File:Claude Monet Painting in his Studio is cc-by-4.0.
    # Attribution-required is a different obligation, not a weaker one.
    assert not is_free_license({"License": {"value": "cc-by-4.0"}})
    assert not is_free_license({"License": {"value": "cc-by-sa-3.0"}})


def test_a_missing_license_id_falls_back_to_the_short_name():
    assert is_free_license({"LicenseShortName": {"value": "Public domain"}})


def test_an_unknown_license_is_not_assumed_free():
    assert not is_free_license({})
    assert not is_free_license({"LicenseShortName": {"value": "No restrictions"}})


# --- authorship -------------------------------------------------------------

def test_a_paintings_by_category_attributes_the_work():
    assert by_artist(["Paintings by Claude Monet"], "Claude Monet")
    assert by_artist(["Featured pictures of paintings by Claude Monet"], "Claude Monet")
    assert by_artist(["Details of paintings by Claude Monet"], "Claude Monet")


def test_a_portrait_of_the_artist_by_someone_else_is_rejected():
    # Live result: Édouard Manet's portrait of Monet sits in a category naming
    # Monet. Containing the name is not authorship.
    assert not by_artist(
        ["Portrait de Claude Monet peignant par Édouard Manet"], "Claude Monet"
    )


def test_no_categories_means_no_attribution():
    assert not by_artist([], "Claude Monet")


def test_matching_is_case_insensitive():
    assert by_artist(["paintings by claude monet"], "Claude Monet")


# --- parsing ----------------------------------------------------------------

def test_an_attributed_public_domain_work_is_kept():
    arts = parse_commons(body(page(categories=["Paintings by Claude Monet"])),
                         "Claude Monet", NOW)
    assert len(arts) == 1
    assert arts[0].title == "Woman with a Parasol"
    assert arts[0].artist == "Claude Monet"


def test_the_uploader_is_never_recorded_as_the_painter():
    # extmetadata.Artist names the photographer; using it would misattribute
    # every work on Commons.
    art = parse_commons(body(page(categories=["Paintings by Claude Monet"])),
                        "Claude Monet", NOW)[0]
    assert "Leclercq" not in art.artist


def test_html_is_stripped_from_the_credit_line():
    art = parse_commons(body(page(categories=["Paintings by Claude Monet"])),
                        "Claude Monet", NOW)[0]
    assert "<" not in art.credit_line


def test_a_cc_by_file_is_excluded_even_when_correctly_attributed():
    assert parse_commons(
        body(page(license_id="cc-by-4.0", short="CC BY 4.0",
                  categories=["Paintings by Claude Monet"])),
        "Claude Monet", NOW,
    ) == []


def test_a_public_domain_file_by_another_painter_is_excluded():
    assert parse_commons(
        body(page(categories=["Portrait de Claude Monet par Édouard Manet"])),
        "Claude Monet", NOW,
    ) == []


def test_an_artist_still_in_copyright_is_excluded_when_the_death_year_is_known():
    assert parse_commons(
        body(page(categories=["Paintings by Pablo Picasso"])),
        "Pablo Picasso", NOW, death_year=1973,
    ) == []


def test_the_thumbnail_is_preferred_over_the_full_resolution_original():
    # Originals run to tens of megabytes; the render only needs 1600px.
    art = parse_commons(body(page(categories=["Paintings by Claude Monet"])),
                        "Claude Monet", NOW)[0]
    assert art.image_url.endswith("thumb.jpg")


# --- search -----------------------------------------------------------------

def test_the_search_restricts_itself_to_the_file_namespace():
    # Without gsrnamespace=6 the search returns articles, not images.
    assert "gsrnamespace=6" in search_url("Monet", 10)


def test_nothing_usable_raises_rather_than_returning_empty():
    with pytest.raises(MissingDataError):
        search_commons(
            "Claude Monet",
            transport=lambda url: body(page(license_id="cc-by-4.0", short="CC BY 4.0")),
            now=NOW,
        )


def test_a_transport_failure_becomes_missing_data():
    def boom(url):
        raise OSError("reset")

    with pytest.raises(MissingDataError):
        search_commons("Monet", transport=boom, now=NOW)


def test_wikidata_markers_are_stripped_from_titles():
    # Commons splices structured-data markers into ObjectName. These reach the
    # screen as a chapter title, so they must not survive.
    from contentforge.sourcing.commons import clean_title

    assert clean_title(
        'At Petit-Gennevillierslabel QS:Lfr,"Au Petit-Gennevilliers"'
    ) == "At Petit-Gennevilliers"
    assert clean_title('Irisestitle QS:P1476,en:"Irises"') == "Irises"
    assert clean_title("A plain title") == "A plain title"
