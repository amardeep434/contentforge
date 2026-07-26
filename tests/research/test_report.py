import json
from datetime import datetime, timezone

import pytest

from contentforge.errors import MissingDataError
from contentforge.provenance import Fact, Provenance
from contentforge.research.changes import ChangeProfile
from contentforge.research.report import write_report
from contentforge.research.score import NicheScore

NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)
LONG_URL = "https://www.googleapis.com/youtube/v3/channels?id=" + ",".join(
    f"UC_{n}" for n in range(50)
)
PROV = Provenance(source_url=LONG_URL, response_id="etag-abc", retrieved_at=NOW)


def a_score(niche="finance"):
    return NicheScore(
        niche=niche, geography="US", score=42.0, rpm_usd=Fact(15.0, PROV),
        sampled_channels=100, breakout_count=12, breakout_rate=0.12,
        median_lift=7.5, membership_factor=1.0,
    )


def a_profile():
    return ChangeProfile(
        duration_before=600, duration_after=60,
        cadence_days_before=10, cadence_days_after=3,
        title_words_before=4, title_words_after=9,
    )


def test_markdown_cites_etag_not_the_giant_url(tmp_path):
    _, md_path = write_report([a_score()], {}, {"etag-abc": {"ok": True}}, tmp_path, NOW)
    text = md_path.read_text()
    assert "etag-abc" in text
    assert LONG_URL not in text, "the 3000-char URL must not appear in the markdown"


def test_markdown_stays_readable(tmp_path):
    _, md_path = write_report([a_score()], {}, {"etag-abc": {"ok": True}}, tmp_path, NOW)
    longest = max(len(line) for line in md_path.read_text().split("\n"))
    assert longest < 300, f"longest line is {longest} chars"


def test_raw_responses_are_written_for_audit(tmp_path):
    write_report([a_score()], {}, {"etag-abc": {"ok": True}}, tmp_path, NOW)
    raw = tmp_path / "raw" / "etag-abc.json"
    assert raw.exists()
    assert json.loads(raw.read_text()) == {"ok": True}


def test_json_retains_full_source_url(tmp_path):
    json_path, _ = write_report([a_score()], {}, {}, tmp_path, NOW)
    payload = json.loads(json_path.read_text())
    assert payload["niches"][0]["rpm_usd"]["source_url"] == LONG_URL


def test_report_records_sample_size_and_breakout_stats(tmp_path):
    json_path, _ = write_report([a_score()], {}, {}, tmp_path, NOW)
    entry = json.loads(json_path.read_text())["niches"][0]
    assert entry["sampled_channels"] == 100
    assert entry["breakout_count"] == 12
    assert entry["breakout_rate"] == pytest.approx(0.12)
    assert entry["median_lift"] == pytest.approx(7.5)


def test_change_section_renders_and_disclaims_causation(tmp_path):
    _, md_path = write_report(
        [a_score()], {"finance": [a_profile()]}, {}, tmp_path, NOW
    )
    text = md_path.read_text()
    assert "600s → 60s" in text
    assert "association, not cause" in text


def test_niche_without_profiles_gets_no_change_section(tmp_path):
    _, md_path = write_report([a_score()], {}, {}, tmp_path, NOW)
    assert "What changed at breakout" not in md_path.read_text()


def test_empty_scores_raise(tmp_path):
    with pytest.raises(MissingDataError):
        write_report([], {}, {}, tmp_path, NOW)
