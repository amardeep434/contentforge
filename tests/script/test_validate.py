from datetime import datetime, timezone

import pytest

from contentforge.script.validate import (
    MAX_OVERLAP_WORDS, ValidationError, check_citations, check_credentials,
    check_verbatim, find_violations, validate_script,
)
from contentforge.sourcing.fetch import Source

NOW = datetime(2026, 7, 27, tzinfo=timezone.utc)
SOURCES = [Source("https://a", "A",
                  "Hot air is circulated by a fan around the food basket at high speed.", NOW)]


def test_script_with_citations_passes():
    validate_script("An air fryer moves heated air quickly [1].", SOURCES)


def test_script_with_no_citations_at_all_is_rejected():
    with pytest.raises(ValidationError, match="citation"):
        check_citations("An air fryer moves heated air quickly.", SOURCES)


def test_citation_pointing_at_a_nonexistent_source_is_rejected():
    with pytest.raises(ValidationError, match="source 7"):
        check_citations("Air moves fast [7].", SOURCES)


def test_verbatim_lift_longer_than_the_cap_is_rejected():
    lifted = "Hot air is circulated by a fan around the food basket at high speed [1]."
    with pytest.raises(ValidationError, match="verbatim"):
        check_verbatim(lifted, SOURCES)


def test_short_shared_phrasing_is_allowed():
    check_verbatim("Hot air is circulated [1] which cooks food evenly.", SOURCES)


def test_paraphrase_passes():
    check_verbatim("A fan pushes heated air around the basket [1].", SOURCES)


def test_case_and_punctuation_do_not_defeat_the_check():
    lifted = "HOT AIR IS CIRCULATED, BY A FAN, AROUND THE FOOD BASKET, AT HIGH SPEED! [1]"
    with pytest.raises(ValidationError, match="verbatim"):
        check_verbatim(lifted, SOURCES)


def test_fabricated_credential_claims_are_rejected():
    with pytest.raises(ValidationError, match="credential"):
        check_credentials("I have spent years studying this topic.")


def test_in_my_experience_is_rejected():
    with pytest.raises(ValidationError, match="credential"):
        check_credentials("In my experience these fail quickly.")


def test_the_cap_is_what_the_test_says_it_is():
    assert MAX_OVERLAP_WORDS == 12


def test_find_violations_is_empty_for_a_clean_script():
    assert find_violations("An air fryer moves heated air quickly [1].", SOURCES) == []


def test_find_violations_collects_all_problems_not_just_the_first():
    # A verbatim lift AND a fabricated credential in one draft: the operator (and
    # the retry) must see both at once, not fix one and re-discover the next.
    script = ("Hot air is circulated by a fan around the food basket at high speed [1]. "
              "I have spent years studying this [1].")
    violations = find_violations(script, SOURCES)
    assert any("verbatim" in v for v in violations)
    assert any("credential" in v for v in violations)


def test_find_violations_reports_a_lifted_span_once_not_every_sliding_window():
    # The 14-word source yields 3 overlapping 12-word windows; a whole-sentence
    # lift must surface as ONE span, not three near-duplicate messages.
    lifted = "Hot air is circulated by a fan around the food basket at high speed [1]."
    verbatim = [v for v in find_violations(lifted, SOURCES) if "verbatim" in v]
    assert len(verbatim) == 1


def test_validate_script_raises_with_every_problem_joined():
    script = ("Hot air is circulated by a fan around the food basket at high speed [1]. "
              "In my experience these fail [1].")
    with pytest.raises(ValidationError) as excinfo:
        validate_script(script, SOURCES)
    message = str(excinfo.value)
    assert "verbatim" in message
    assert "credential" in message
