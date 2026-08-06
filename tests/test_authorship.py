"""Is a channel a faceless operation, or a person?

Written from the real case: Art History Explained was selected as this project's
exemplar and turned out to be an art writer narrating his own work, with the
evidence sitting in the video description the whole time (C-048).
"""

from contentforge.research.authorship import (
    FACELESS,
    PERSONAL,
    UNKNOWN,
    check_channel,
    classify_operator,
)

# The actual description that gave it away.
REAL_DESCRIPTION = """
If you're a fan of Cezanne and you liked this video, do leave a comment below.
Loved this video? You can leave me a tip at: https://ko-fi.com/christopherpjones
Fancy more? You can also join my newsletter on Substack here:
https://christopherpjones.substack.com
"""


def test_the_case_that_prompted_this_is_caught():
    verdict = classify_operator(REAL_DESCRIPTION)
    assert verdict.kind == PERSONAL
    assert verdict.is_personal
    assert "ko-fi" in verdict.evidence


def test_a_tip_jar_alone_is_enough():
    # Faceless channels take ad revenue; they do not ask for tips.
    assert classify_operator("support me at patreon.com/someone").kind == PERSONAL
    assert classify_operator("buymeacoffee.com/x").kind == PERSONAL


def test_a_personal_newsletter_is_enough():
    assert classify_operator("read more at foo.substack.com").kind == PERSONAL


def test_first_person_authorship_is_caught():
    assert classify_operator("Follow me on Twitter for more").kind == PERSONAL
    assert classify_operator("I'm a writer based in London").kind == PERSONAL
    assert classify_operator("Written and narrated by me").kind == PERSONAL


def test_nothing_found_is_unknown_not_faceless():
    # The whole point. Absence of a tip jar is not evidence of absence of a
    # person, and calling it FACELESS would relaunch the mistake this check
    # exists to prevent.
    verdict = classify_operator("Subscribe for more space facts every week.")
    assert verdict.kind == UNKNOWN
    assert verdict.kind != FACELESS
    assert "not proof" in verdict.evidence


def test_no_description_is_unknown():
    assert classify_operator("").kind == UNKNOWN
    assert classify_operator("   ").kind == UNKNOWN


def test_a_generic_channel_plug_is_not_a_personal_signal():
    # "our channel" and a merch link are not authorship claims.
    assert classify_operator("Check out our channel for more!").kind == UNKNOWN


def test_evidence_is_reported_so_a_human_can_check_it():
    verdict = classify_operator(REAL_DESCRIPTION)
    assert "substack" in verdict.evidence
    assert len(verdict.evidence) > 10


def test_check_channel_uses_the_injected_fetcher():
    seen = {}

    def fetcher(url, videos):
        seen["url"] = url
        seen["videos"] = videos
        return REAL_DESCRIPTION

    verdict = check_channel("https://youtube.com/@x", fetcher=fetcher, videos=5)
    assert seen == {"url": "https://youtube.com/@x", "videos": 5}
    assert verdict.kind == PERSONAL


def test_a_fetch_failure_is_unknown_rather_than_an_exception():
    # A channel that cannot be fetched must not stop a research run.
    assert check_channel("x", fetcher=lambda url, videos: "").kind == UNKNOWN


def test_the_url_is_built_from_an_id_never_a_handle():
    # A guessed handle 404s and the check then silently reports UNKNOWN - safe
    # but useless. Handle-guessing is 5-for-5 wrong in this project (C-008).
    import pytest

    from contentforge.research.authorship import channel_url

    assert channel_url("UC1I3jchpTW8mvQkzV-fmFoQ").endswith("/videos")
    assert "UC1I3jchpTW8mvQkzV-fmFoQ" in channel_url("UC1I3jchpTW8mvQkzV-fmFoQ")
    with pytest.raises(ValueError):
        channel_url("ArtHistoryExplained")
    with pytest.raises(ValueError):
        channel_url("@ArtHistoryExplained")


NETWORK_DESCRIPTION = """
My Other Channel: @HowMoneyWorks @HowBusinessWorked
Edited By: Svibe Multimedia Studio
Music Courtesy of: Epidemic Sound
Select Footage Courtesy of: Getty Images
Business Inquiries: sponsors@worksmedia.group
"""


def test_a_media_network_is_caught():
    # The first version of this classifier looked only for tip jars and
    # newsletters, so it reported UNKNOWN for a four-channel operation with an
    # outsourced editing studio and paid Getty licences.
    from contentforge.research.authorship import NETWORK

    verdict = classify_operator(NETWORK_DESCRIPTION)
    assert verdict.kind == NETWORK
    assert not verdict.reproducible


def test_individual_signals_each_suffice():
    from contentforge.research.authorship import NETWORK

    for text in (
        "My other channel: @Something",
        "Edited by Some Studio",
        "Business inquiries: hi@company.com",
        "Footage courtesy of Getty Images",
        "Music from Epidemic Sound",
    ):
        assert classify_operator(text).kind == NETWORK, text


def test_a_personal_signal_outranks_a_network_one():
    # A tip jar is the more specific finding; report that.
    assert classify_operator(
        "Tip me at ko-fi.com/x — Edited by A Studio"
    ).kind == PERSONAL


def test_a_plain_faceless_description_is_still_unknown():
    verdict = classify_operator("Subscribe for more space facts every week.")
    assert verdict.kind == UNKNOWN
    assert verdict.reproducible
