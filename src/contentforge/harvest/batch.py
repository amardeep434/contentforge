from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from contentforge import interrupt
from contentforge.pipeline import run_dir_for


def run_batch(entries, niche, root, build_one, channel="channel", *, arm=interrupt.arm):
    arm()
    root = Path(root)
    ledger = {e.slug: {"status": "pending"} for e in entries}
    log_dir = root / niche / "harvest" / channel
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / "harvest-make.log"

    def flush():
        (log_dir / "batch.json").write_text(json.dumps(ledger, indent=2))

    def note(line):
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with log.open("a", encoding="utf-8") as fh:
            fh.write(f"{stamp} {line}\n")

    flush()
    for entry in entries:
        final = run_dir_for(root, niche, entry.slug) / "final" / "video.mp4"
        if final.exists():
            ledger[entry.slug] = {"status": "done"}
            note(f"{entry.slug}: skip (already done)"); flush(); continue
        ledger[entry.slug] = {"status": "running"}; flush()
        try:
            build_one(entry)
        except interrupt.StopRequested:
            ledger[entry.slug] = {"status": "stopped"}
            note(f"{entry.slug}: STOPPED (batch)"); flush()
            break
        except Exception as exc:                       # one bad video must not kill the batch
            ledger[entry.slug] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
            note(f"{entry.slug}: FAILED - {exc}"); flush(); continue
        ledger[entry.slug] = {"status": "done"}
        note(f"{entry.slug}: done"); flush()
    return ledger
