import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from contentforge.errors import MissingDataError
from contentforge.sourcing.fetch import Source, fetch_source, load_sources, save_sources

NOW = datetime(2026, 7, 27, tzinfo=timezone.utc)


def test_fetch_captures_text_and_provenance():
    markup = "<html><title>How Air Fryers Work</title><body>Hot air circulates.</body></html>"
    source = fetch_source("https://example.org/airfryer", lambda u: markup, NOW)
    assert "Hot air circulates" in source.text
    assert source.title == "How Air Fryers Work"
    assert source.retrieved_at == NOW


def test_script_and_style_blocks_are_stripped():
    markup = "<html><body><script>var x=1;</script><p>Real text</p></body></html>"
    assert "var x" not in fetch_source("https://e", lambda u: markup, NOW).text


def test_empty_page_raises_rather_than_storing_nothing():
    with pytest.raises(MissingDataError):
        fetch_source("https://example.org/x", lambda u: "", NOW)


def test_sources_round_trip_through_disk(tmp_path):
    sources = [Source("https://a", "A", "text a", NOW), Source("https://b", "B", "text b", NOW)]
    save_sources(sources, tmp_path)
    loaded = load_sources(tmp_path)
    assert [s.url for s in loaded] == ["https://a", "https://b"]
    assert loaded[0].text == "text a"


def test_loading_an_empty_directory_raises():
    with tempfile.TemporaryDirectory() as empty:
        with pytest.raises(MissingDataError):
            load_sources(Path(empty))
