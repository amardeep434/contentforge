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
