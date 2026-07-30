# scripts/

Exploratory analysis scripts. Not part of the package, not covered by the test
suite — kept because the findings in `docs/findings/` are only as trustworthy as
the code that produced them, and rerunning beats re-deriving.

Each reads `YOUTUBE_API_KEY` from the environment (`.env` at the repo root) and
writes CSV to paths given by environment variables. Run from the repo root with
the project venv.

## scan_channels.py

Profiles YouTube channels on **median views, hit-rate and skew** — never mean.
See C-001 and C-003 in [claims-ledger.md](../docs/findings/claims-ledger.md) for
why the mean is unusable.

```bash
set -a; . ./.env; set +a
SCAN_OUT=out/profiles.csv CANDS_OUT=out/candidates.csv .venv/bin/python scripts/scan_channels.py
```

Cost is dominated by search: 100 units per niche, ~2 units per channel profiled.
A 24-niche run over 146 channels cost 2,791 units of the 10,000/day quota.

Writes two files. `CANDS_OUT` records **every channel found, gated or not**, so a
later re-filter costs nothing. Rev 1 of this script omitted that and had to be
re-searched at full price when its filtering turned out to be wrong.

The `QUOTA_STOP` constant leaves headroom; the script exits cleanly and keeps
partial results when it trips, because a mid-run quota death otherwise loses
everything spent so far.

## hit_flop_extremes.py

Given a profile CSV, lists each channel's top-3 and bottom-3 long-form videos.
Feeds the within-channel comparison that C-005 rests on.

```bash
SCAN=out/profiles.csv OUT=out/extremes.csv .venv/bin/python scripts/hit_flop_extremes.py
```

**Age-match before comparing** (C-006). Views accumulate, so a channel whose hits
are two years old and whose flops are two months old will show a difference that
is entirely publication date. Air Crash Investigation was excluded from the
2026-07-29 analysis for exactly this reason.

## Reading captions

Not a script — captions come from `yt-dlp` directly and cost **no API quota**:

```bash
yt-dlp --write-auto-sub --sub-lang "en.*" --skip-download --sub-format vtt -o NAME "URL"
```

The entire cross-channel script-structure test cost 10 units, all of it spent
listing videos rather than reading them.
