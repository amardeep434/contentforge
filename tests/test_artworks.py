"""Public-domain artwork sourcing.

The licence gate is the whole point of this module. C-033 holds only for artworks
that are themselves public domain; an artist still in copyright turns a free,
legal asset into an infringement. Every check here fails closed.
"""

import json
from datetime import datetime, timezone

import pytest

from contentforge.errors import MissingDataError
from contentforge.sourcing.artworks import (
    Artwork,
    assert_public_domain,
    death_year_from,
    death_year_of,
    parse_artwork,
    search_artworks,
)

NOW = datetime(2026, 7, 30, tzinfo=timezone.utc)


def record(**over):
    base = {
        "title": "The Card Players",
        "artistDisplayName": "Paul Cézanne",
        "artistBeginDate": "1839",
        "artistEndDate": "1906",
        "objectDate": "1890–92",
        "isPublicDomain": True,
        "creditLine": "Bequest of Stephen C. Clark, 1960",
        "primaryImage": "https://images.metmuseum.org/CRDImages/ep/original/DP231550.jpg",
        "objectURL": "https://www.metmuseum.org/art/collection/search/435868",
    }
    base.update(over)
    return base


# --- the licence gate -------------------------------------------------------

def test_an_artist_dead_over_seventy_years_passes():
    assert_public_domain(1906, NOW)          # Cezanne
    assert_public_domain(1944, NOW)          # Kandinsky


def test_an_artist_still_in_copyright_raises():
    # Picasso died 1973; not public domain until after 2043.
    with pytest.raises(MissingDataError, match="1973"):
        assert_public_domain(1973, NOW)


def test_an_unknown_death_year_raises_rather_than_assuming():
    # "We could not establish it" must never become "it is probably fine".
    with pytest.raises(MissingDataError):
        assert_public_domain(None, NOW)


def test_the_boundary_year_is_not_waved_through():
    # life + 70 expires at the END of the 70th year, so 1956 is not clear in
    # 2026. An off-by-one here is an infringement, so it fails closed.
    with pytest.raises(MissingDataError):
        assert_public_domain(1956, NOW)
    assert_public_domain(1955, NOW)


# --- reading the death year -------------------------------------------------

def test_the_structured_field_is_preferred():
    assert death_year_of(record(artistEndDate="1906")) == 1906


def test_a_living_artist_has_no_death_year():
    assert death_year_of(record(artistEndDate="", artistDisplayName="Jeff Koons")) is None


def test_a_zero_end_date_is_not_a_death_year():
    # The Met uses "0" for unknown. Treating it as a year would clear every
    # such artwork as two millennia old.
    assert death_year_of(record(artistEndDate="0", artistDisplayName="Unknown")) is None


def test_it_falls_back_to_parsing_a_lifespan_string():
    assert death_year_of(
        record(artistEndDate="", artistDisplayName="Paul Cezanne (French, 1839–1906)")
    ) == 1906


def test_lifespan_parsing_needs_a_birth_and_a_death():
    assert death_year_from("Jeff Koons (American, born 1955)") is None
    assert death_year_from("Wassily Kandinsky (1866-1944)") == 1944
    assert death_year_from("Unknown") is None


# --- parsing ----------------------------------------------------------------

def test_a_public_domain_artwork_is_parsed_with_its_credit_line():
    art = parse_artwork(record(), NOW)
    assert isinstance(art, Artwork)
    assert art.title == "The Card Players"
    assert art.artist == "Paul Cézanne"
    assert art.year == "1890–92"
    # C-033's caveat: museums impose contractual terms even where copyright has
    # expired, and this field is the only record of them.
    assert art.credit_line == "Bequest of Stephen C. Clark, 1960"
    assert art.source.startswith("https://www.metmuseum.org/")
    assert art.retrieved_at == NOW


def test_an_artwork_not_flagged_public_domain_is_excluded():
    assert parse_artwork(record(isPublicDomain=False), NOW) is None


def test_a_missing_flag_is_not_treated_as_true():
    incomplete = record()
    del incomplete["isPublicDomain"]
    assert parse_artwork(incomplete, NOW) is None


def test_a_truthy_string_is_not_treated_as_the_boolean():
    assert parse_artwork(record(isPublicDomain="true"), NOW) is None


def test_an_artwork_without_an_image_is_excluded():
    assert parse_artwork(record(primaryImage=""), NOW) is None


def test_an_artwork_by_an_artist_in_copyright_is_excluded():
    assert parse_artwork(
        record(artistDisplayName="Pablo Picasso", artistEndDate="1973"), NOW
    ) is None


# --- search -----------------------------------------------------------------

def transport_for(ids, obj):
    def _transport(url):
        if "/search" in url:
            return json.dumps({"objectIDs": ids})
        return json.dumps(obj)

    return _transport


def test_search_fetches_each_object_and_keeps_the_passing_ones():
    arts = search_artworks("cezanne", transport=transport_for([1, 2], record()), now=NOW)
    assert len(arts) == 2


def test_search_stops_once_the_limit_is_met():
    calls = []

    def _transport(url):
        calls.append(url)
        if "/search" in url:
            return json.dumps({"objectIDs": list(range(50))})
        return json.dumps(record())

    search_artworks("Cezanne", transport=_transport, now=NOW, limit=3)
    assert len([c for c in calls if "/objects/" in c]) == 3


def test_one_unreachable_object_does_not_lose_the_whole_search():
    def _transport(url):
        if "/search" in url:
            return json.dumps({"objectIDs": [1, 2]})
        if url.endswith("/1"):
            raise OSError("timeout")
        return json.dumps(record())

    assert len(search_artworks("Cezanne", transport=_transport, now=NOW)) == 1


def test_nothing_usable_raises_rather_than_returning_empty():
    # An empty list would let a video render with no visuals at all.
    with pytest.raises(MissingDataError):
        search_artworks(
            "Cezanne",
            transport=transport_for([1], record(isPublicDomain=False)),
            now=NOW,
        )


def test_search_propagates_a_transport_failure_as_missing_data():
    def boom(url):
        raise OSError("connection reset")

    with pytest.raises(MissingDataError):
        search_artworks("x", transport=boom, now=NOW)


# --- artist matching --------------------------------------------------------

def test_another_painters_work_is_not_accepted():
    # The Met's free-text search returns unrelated artists; putting a Guido
    # Reni in a Klimt video looks like success and is not.
    from contentforge.sourcing.artworks import artist_matches

    assert artist_matches(record(artistDisplayName="Guido Reni"), "Klimt") is False
    assert artist_matches(record(artistDisplayName="Paul Cezanne"), "Cezanne") is True


def test_accents_do_not_break_matching():
    # The Met writes "Cézanne"; nobody types it that way. Requiring an exact
    # match here would silently reject every artwork by the artist.
    from contentforge.sourcing.artworks import artist_matches

    assert artist_matches(record(artistDisplayName="Paul Cézanne"), "Cezanne") is True


def test_matching_works_in_either_direction():
    from contentforge.sourcing.artworks import artist_matches

    assert artist_matches(record(artistDisplayName="Paul Cezanne"), "Paul Cezanne")
    assert artist_matches(record(artistDisplayName="Paul Cezanne"), "cezanne")


def test_an_artwork_with_no_artist_is_not_matched():
    from contentforge.sourcing.artworks import artist_matches

    assert artist_matches(record(artistDisplayName=""), "Cezanne") is False


def test_search_rejects_results_by_other_artists():
    def _transport(url):
        if "/search" in url:
            return json.dumps({"objectIDs": [1]})
        return json.dumps(record(artistDisplayName="Guido Reni"))

    with pytest.raises(MissingDataError, match="collection may not hold"):
        search_artworks("Klimt", transport=_transport, now=NOW)


def test_survey_reports_zero_without_raising():
    # Availability is the question being asked, so "none" is an answer here
    # rather than an error - unlike search_artworks, which must not hand back
    # an empty set to a renderer.
    from contentforge.sourcing.artworks import survey_artists

    def _transport(url):
        if "/search" in url:
            return json.dumps({"objectIDs": [1]})
        return json.dumps(record(isPublicDomain=False))

    assert survey_artists(["Monet"], transport=_transport, now=NOW) == {"Monet": 0}
