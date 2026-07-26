import json
from datetime import datetime, timezone

import pytest

from contentforge.errors import MissingDataError
from contentforge.provenance import Fact, Provenance
from contentforge.research.metrics import NicheMetrics
from contentforge.research.report import write_report
from contentforge.research.score import score_niche

NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)
PROV = Provenance(source_url="https://src.example/rpm", response_id="r", retrieved_at=NOW)


def a_score(niche="finance"):
    metrics = NicheMetrics(
        niche=niche,
        competitor_count=Fact(4, PROV),
        median_views_per_day=Fact(100.0, PROV),
        entrability=Fact(0.5, PROV),
    )
    return score_niche(metrics, Fact(2.0, PROV), "US")


def test_writes_both_files(tmp_path):
    json_path, md_path = write_report([a_score()], tmp_path, NOW)
    assert json_path.exists()
    assert md_path.exists()


def test_json_records_every_source_url(tmp_path):
    json_path, _ = write_report([a_score()], tmp_path, NOW)
    payload = json.loads(json_path.read_text())
    entry = payload["niches"][0]
    assert entry["rpm_usd"]["source_url"] == "https://src.example/rpm"
    assert entry["metrics"]["competitor_count"]["source_url"] == "https://src.example/rpm"
    assert entry["metrics"]["median_views_per_day"]["source_url"] == "https://src.example/rpm"
    assert entry["metrics"]["entrability"]["source_url"] == "https://src.example/rpm"


def test_json_records_retrieval_timestamps(tmp_path):
    json_path, _ = write_report([a_score()], tmp_path, NOW)
    payload = json.loads(json_path.read_text())
    assert payload["niches"][0]["rpm_usd"]["retrieved_at"] == NOW.isoformat()
    assert payload["generated_at"] == NOW.isoformat()


def test_markdown_includes_source_links(tmp_path):
    _, md_path = write_report([a_score()], tmp_path, NOW)
    text = md_path.read_text()
    assert "https://src.example/rpm" in text
    assert "finance" in text


def test_markdown_numbers_ranks_in_order(tmp_path):
    _, md_path = write_report([a_score("finance"), a_score("tech")], tmp_path, NOW)
    text = md_path.read_text()
    assert text.index("1. finance") < text.index("2. tech")


def test_empty_score_list_raises_rather_than_writing_empty_report(tmp_path):
    with pytest.raises(MissingDataError):
        write_report([], tmp_path, NOW)


def test_creates_output_directory_if_absent(tmp_path):
    target = tmp_path / "nested" / "deeper"
    json_path, _ = write_report([a_score()], target, NOW)
    assert json_path.exists()
