import pytest
from contentforge.harvest.transcripts import vtt_to_text, fetch_transcript
from contentforge.errors import MissingDataError

VTT = """WEBVTT

00:00:00.000 --> 00:00:02.000
Owning a laundromat looks easy.

00:00:02.000 --> 00:00:04.000
The reality is a drain at midnight.
"""

def test_vtt_to_text_strips_timing_and_headers():
    assert vtt_to_text(VTT) == "Owning a laundromat looks easy. The reality is a drain at midnight."

def test_vtt_to_text_decodes_html_entities():
    vtt = """WEBVTT

00:00:00.000 --> 00:00:02.000
It&#39;s rock &amp; roll &gt; everything &lt; else.
"""
    assert vtt_to_text(vtt) == "It's rock & roll > everything < else."

def test_vtt_to_text_strips_webvtt_header_with_suffix():
    vtt = """WEBVTT - Kind: captions, Language: en

00:00:00.000 --> 00:00:02.000
Hello there.
"""
    assert vtt_to_text(vtt) == "Hello there."

def _runner_that_writes(vid="abc123"):
    # yt-dlp writes <dir>/<id>.en.vtt; the fake runner mimics that by reading the
    # -o template out of the command and writing the VTT file there.
    import os
    from pathlib import Path
    def run(cmd, **kwargs):
        out_template = cmd[cmd.index("-o") + 1]        # ".../%(id)s.%(ext)s"
        Path(os.path.dirname(out_template), f"{vid}.en.vtt").write_text(VTT, encoding="utf-8")
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()
    return run

def test_fetch_transcript_reads_downloaded_vtt():
    got = fetch_transcript("abc123", runner=_runner_that_writes())
    assert got == "Owning a laundromat looks easy. The reality is a drain at midnight."

def test_fetch_transcript_no_captions_raises():
    def run(cmd, **kwargs):                              # writes no file
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()
    with pytest.raises(MissingDataError, match="abc123"):
        fetch_transcript("abc123", runner=run)

def test_fetch_transcript_extracts_id_from_full_url_with_playlist():
    # watch?v=abc123&list=PLxxx must resolve to "abc123", not "PLxxx" - the
    # id is used both for the yt-dlp URL/filename and for error messages.
    def run(cmd, **kwargs):                              # writes no file
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()
    with pytest.raises(MissingDataError, match="abc123"):
        fetch_transcript("https://www.youtube.com/watch?v=abc123&list=PLxxx", runner=run)

def test_fetch_transcript_uses_no_playlist_flag():
    seen = {}
    def run(cmd, **kwargs):
        seen["cmd"] = cmd
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()
    with pytest.raises(MissingDataError):
        fetch_transcript("abc123", runner=run)
    assert "--no-playlist" in seen["cmd"]

def test_fetch_transcript_yt_dlp_failure_raises_with_stderr():
    def run(cmd, **kwargs):                              # simulates a real failure
        class R:
            returncode = 1
            stdout = ""
            stderr = "ERROR: Video unavailable"
        return R()
    with pytest.raises(MissingDataError, match="Video unavailable"):
        fetch_transcript("abc123", runner=run)

def test_fetch_transcript_empty_text_raises():
    def run(cmd, **kwargs):
        import os
        from pathlib import Path
        out_template = cmd[cmd.index("-o") + 1]
        # vtt file exists but contains no cue text at all
        Path(os.path.dirname(out_template), "abc123.en.vtt").write_text("WEBVTT\n", encoding="utf-8")
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()
    with pytest.raises(MissingDataError, match="abc123"):
        fetch_transcript("abc123", runner=run)
