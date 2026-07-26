import pytest

from contentforge.cli import _redact


def test_redact_strips_api_keys_from_error_text():
    raw = (
        "<HttpError 404 when requesting https://youtube.googleapis.com/youtube/v3/"
        "playlistItems?playlistId=UU_x&key=AIzaSyCabcdefgh12345&alt=json returned ...>"
    )
    cleaned = _redact(raw)
    assert "AIzaSyCabcdefgh12345" not in cleaned
    assert "key=REDACTED" in cleaned


def test_redact_leaves_other_text_intact():
    assert _redact("playlistId=UU_x") == "playlistId=UU_x"
