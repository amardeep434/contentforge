from pathlib import Path
from contentforge.harvest.plan import HarvestEntry
from contentforge.harvest.batch import run_batch
from contentforge import interrupt

def _entries():
    return [HarvestEntry(f"s{i}", f"T{i}", f"v{i}", f"http://x/v{i}", f"T{i}") for i in (1, 2, 3)]

def test_batch_skips_done_continues_on_fail_records_ledger(tmp_path):
    import json
    root = tmp_path
    # pre-make s1 "done": create its final/video.mp4
    done = root / "biz" / "videos" / "s1" / "final"
    done.mkdir(parents=True); (done / "video.mp4").write_bytes(b"x")
    calls = []
    def build_one(entry):
        calls.append(entry.slug)
        if entry.slug == "s2":
            raise RuntimeError("bad transcript")
    interrupt.clear()
    ledger = run_batch(_entries(), "biz", root, build_one, channel="chan", arm=lambda: None)
    assert calls == ["s2", "s3"]            # s1 skipped (already done)
    assert ledger["s1"]["status"] == "done"
    assert ledger["s2"]["status"] == "failed" and "bad transcript" in ledger["s2"]["error"]
    assert ledger["s3"]["status"] == "done"
    saved = json.loads((root / "biz" / "harvest" / "chan" / "batch.json").read_text())
    assert saved == ledger

def test_batch_stops_on_interrupt(tmp_path):
    def build_one(entry):
        if entry.slug == "s2":
            raise interrupt.StopRequested()
    interrupt.clear()
    ledger = run_batch(_entries(), "biz", tmp_path, build_one, channel="chan", arm=lambda: None)
    assert ledger["s1"]["status"] == "done"
    assert ledger["s2"]["status"] == "stopped"
    assert ledger["s3"]["status"] == "pending"      # not reached
