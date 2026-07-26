from datetime import datetime, timezone

import pytest

from contentforge.errors import MissingDataError
from contentforge.providers.quota import QuotaLedger
from contentforge.providers.youtube_api import YouTubeClient
from contentforge.research.verify import CLAIM_TOLERANCE, check_claim, format_check


def transport_for(views, subs=1000, videos=10, title="Test Channel"):
    def transport(endpoint, params):
        assert endpoint == "channels.list"
        assert "forHandle" in params, "handle lookup costs 1 unit; search costs 100"
        return {
            "etag": "chan-1",
            "items": [
                {
                    "id": "UC_test",
                    "snippet": {"title": title, "publishedAt": "2024-03-30T00:00:00Z"},
                    "statistics": {
                        "subscriberCount": str(subs),
                        "viewCount": str(views),
                        "videoCount": str(videos),
                    },
                }
            ],
        }

    return transport


def test_exact_claim_verifies():
    client = YouTubeClient(api_key="k", transport=transport_for(6_132_088))
    check, ledger = check_claim(client, "@itsjustcars", QuotaLedger(), claimed_views=6_000_000)
    assert check.verdict == "VERIFIED"
    assert abs(check.view_error) < CLAIM_TOLERANCE
    assert ledger.spent == 1, "handle lookup must cost 1 unit, not 100"


def test_leading_at_sign_is_optional():
    client = YouTubeClient(api_key="k", transport=transport_for(1000))
    a, _ = check_claim(client, "@name", QuotaLedger())
    b, _ = check_claim(client, "name", QuotaLedger())
    assert a.channel.title == b.channel.title


def test_overstated_claim_is_flagged():
    client = YouTubeClient(api_key="k", transport=transport_for(1_000_000))
    check, _ = check_claim(client, "@x", QuotaLedger(), claimed_views=10_000_000)
    assert check.verdict == "OVERSTATED"
    assert check.view_error < 0


def test_understated_claim_is_distinguished_from_overstated():
    """A channel that grew since the post is not the same as a false claim."""
    client = YouTubeClient(api_key="k", transport=transport_for(327_518))
    check, _ = check_claim(client, "@x", QuotaLedger(), claimed_views=176_000)
    assert check.verdict.startswith("UNDERSTATED")


def test_implied_earnings_are_labelled_as_not_measured():
    client = YouTubeClient(api_key="k", transport=transport_for(6_000_000))
    check, _ = check_claim(client, "@x", QuotaLedger(), assumed_rpm=5.0)
    assert check.implied_earnings_usd == pytest.approx(30_000)
    assert "not a measurement" in check.note


def test_no_rpm_given_means_no_earnings_figure_at_all():
    client = YouTubeClient(api_key="k", transport=transport_for(6_000_000))
    check, _ = check_claim(client, "@x", QuotaLedger())
    assert check.implied_earnings_usd is None
    assert "not observable" in check.note


def test_views_per_video_is_computed():
    client = YouTubeClient(api_key="k", transport=transport_for(2_475_477, videos=2))
    check, _ = check_claim(client, "@x", QuotaLedger())
    assert check.channel.views_per_video == pytest.approx(1_237_738.5)


def test_zero_videos_does_not_divide_by_zero():
    client = YouTubeClient(api_key="k", transport=transport_for(0, videos=0))
    check, _ = check_claim(client, "@x", QuotaLedger())
    assert check.channel.views_per_video == 0.0


def test_unknown_handle_raises():
    def empty(endpoint, params):
        return {"etag": "e", "items": []}

    client = YouTubeClient(api_key="k", transport=empty)
    with pytest.raises(MissingDataError):
        check_claim(client, "@nobody", QuotaLedger())


def test_format_check_is_readable():
    client = YouTubeClient(api_key="k", transport=transport_for(6_132_088, videos=142))
    check, _ = check_claim(client, "@x", QuotaLedger(), claimed_views=6_000_000, assumed_rpm=5.0)
    text = format_check(check)
    assert "6,132,088" in text
    assert "VERIFIED" in text
    assert "not a measurement" in text
