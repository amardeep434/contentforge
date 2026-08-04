# contentforge

Evidence-grounded pipeline for faceless video content: research → sourced script
→ voice → render → publish.

Status: **research complete, production in progress.** The niche is chosen
([art history](docs/findings/2026-07-30-niche-recommendation.md)) and the build
plan is [Plan 3](docs/superpowers/plans/2026-07-30-art-history-slice.md).

> **Read [`docs/findings/claims-ledger.md`](docs/findings/claims-ledger.md) before
> acting on any research claim.** 43 claims, each with a status — `CONFIRMED`,
> `HYPOTHESIS`, `REFUTED`, `WITHDRAWN` — a sample size, and what changed it.
> Several claims in the spec and the older findings are refuted; **the ledger is
> authoritative wherever they disagree.**

## Principles

1. **Provenance or nothing.** Every factual claim resolves to a source with a URL
   and retrieval timestamp. Stages that lose their inputs fail loudly and write
   nothing — there are no synthesised fallbacks anywhere in this codebase.
2. **Unknown must never read as zero.** A missing measurement is recorded as
   unknown. A zero that means "no data" is how a run once sailed past an
   exhausted quota.
3. **Sample size is part of a claim.** Anything under n≈10 is a hypothesis
   however clean it looks. Three separate conclusions here died from being read
   off n=4.
4. **Correct in place.** When evidence flips a claim, the existing row is edited
   and the refutation attached. The history is the point.
5. **Transform, never relay.** Scripts must not reproduce source material
   verbatim. Enforced in code, not convention.
6. **Scraping and publishing never share credentials.**

## Running

    python -m venv .venv && .venv/bin/pip install -e .
    cp .env.example .env        # then put your YOUTUBE_API_KEY in it
    set -a && . ./.env && set +a

Tests never touch a live API, a GPU or ffmpeg — every backend is injected:

    .venv/bin/pytest            # 536 tests

### Making a video

    pipeline doctor                                   # what this machine can run
    pipeline make my-video --topic 'how ceiling fans work' --source URL --source URL
    pipeline make my-video --script-file script.txt    # or hand-write the script
    pipeline publish my-video                          # private by default, asks first

One command, one run directory, resumable stages:

    script → spec → audio → draw → letter → render

`script` is either hand-written (`--script-file`), generated from `--topic` +
`--source` URLs (grounded in them, checked for verbatim lifting), or a cached
`script.txt`. `render` also emits `subtitles.srt`/`.vtt` from the same shot
timing. `publish` derives the title, description and tags, builds the thumbnail
from the first frame, and uploads — private, behind a confirmation.

Each stage writes a named artefact and is skipped if it is already there, so a
rerun after a crash resumes rather than restarting. `--force draw` redoes one
stage. `spec.json` is the visual plan and is meant to be edited by hand — it is
the cheapest place to fix a video.

The lettering, the drawn sheet it sits on and the palette correction are all
production stages, not post-processing: measured against a native frame from the
reference channel, the gap was never resolution (C-060), it was that theirs
carries a legible document and a flat cream background and ours did not.

Full walkthrough: [docs/setup/running-the-pipeline.md](docs/setup/running-the-pipeline.md).
Publishing: [docs/setup/publishing.md](docs/setup/publishing.md).
GPU setup: [docs/setup/local-image-generation.md](docs/setup/local-image-generation.md).

### Research

Say "research" to an agent and the [`research` skill](.claude/skills/research/SKILL.md)
runs the whole loop. By hand it is four stages:

    pipeline leads "faceless youtube" --source reddit --subreddit aitubers
    pipeline leads "faceless youtube" --source threads --expand
    #  ↳ then read the screenshots and record any channel handles
    pipeline leads-resolve  data/leads/<run>     # API,  ~2 units per channel
    pipeline leads-analyse  data/leads/<run>     # free, re-runnable

Two sources, deliberately. Reddit returns the whole post body and a score;
Threads hides its detail in reply screenshots but is where the earnings claims
and Studio screenshots live (C-043). Threads needs nothing; Reddit needs the
OpenCLI browser bridge.

`leads-analyse` is a pure function over stored measurements, so **changing the
criteria costs no quota**. Criteria have already changed four times.

### Standing state

    pipeline potentials         # every channel measured, with a verdict and why
    pipeline seen --todo        # leads whose screenshots still need reading
    pipeline quota              # local forecast + authoritative reading
    pipeline verify @handle     # check one claimed statistic, 1 unit

### Cost

10,000 quota units/day, resetting at **Pacific** midnight — not UTC, not local.
`search.list` costs 100; `channels.list` with `forHandle` costs 1 and is exact.
Never resolve a channel by search: handle-guessing is 4-for-4 wrong (C-008).

## Layout

    providers/     API clients
      youtube_api.py       Data API v3, every record provenanced
      threads_research.py  Threads via Jina Reader — no key, no quota
      reddit_research.py   Reddit via the OpenCLI browser bridge
      llm.py               OpenAI-compatible, base_url from config
      quota*.py            persistent ledger + authoritative Cloud Monitoring read
    research/      the research loop
      leads.py             gather claims + screenshots
      analytics.py         pure: measurements → verdict + reason
      potentials.py        the cumulative verified-channel list
      seen.py              what happened to every lead, across runs
    sourcing/      primary source gathering
    script/        generation + the provenance validator
    voice/         TTS                          (Plan 3, task 2)
    visuals/       artwork sourcing + shots     (Plan 3, tasks 1, 3, 5)
    render/        ffmpeg composition           (Plan 3, task 4)
    publish/       platform upload              (Plan 3, task 6)

## Where things are written

    docs/findings/claims-ledger.md    what we believe, and why — start here
    docs/findings/*.md                the evidence behind each claim
    docs/evidence/potentials.csv      every channel measured, with a verdict
    docs/evidence/leads-seen.csv      every post gathered and what became of it
    docs/evidence/2026-07-29/         raw scan CSVs, 1,189 candidates
    docs/superpowers/specs/           design
    docs/superpowers/plans/           implementation plans
    data/leads/<run>/                 gitignored; screenshots are regenerable

Nothing that cost effort lives only in a gitignored directory.

## What the research concluded

Eight externally-visible hypotheses were tested and refuted — mean-based
ranking, format, asset polish, cut rate, production tooling, narration timing,
opener formula, opening style. Of 177 channels profiled, **one** is both
repeatable and small enough to infer from.

The variable that would explain the rest — click-through against impressions —
is visible only to a channel's owner (C-028). So further observational research
has negative expected value, and the next evidence has to come from our own
uploads. That is what Plan 3 is for.

## License

Private. All rights reserved.
