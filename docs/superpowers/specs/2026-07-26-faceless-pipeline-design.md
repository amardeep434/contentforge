# contentforge — Design

**Date:** 2026-07-26
**Status:** Approved, pending implementation plan

## 1. Goal

Produce faceless video content that reaches YouTube monetization, using Shorts for discovery and long-form for revenue, with Instagram Reels and Threads as additional distribution. Operate at near-zero cost until the channel earns. The pipeline must be reusable for client work later, so nothing is hardcoded to one channel or niche.

## 2. Constraints

| Constraint | Value |
|---|---|
| Budget | ~zero until revenue. No paid APIs, no stock subscriptions, no paid TTS. |
| Operator time | 1–2 hrs/week, approve/reject only. Trending toward hands-off. |
| Data access | YouTube Data API v3 (free, 10k units/day). instagrapi login scraping (authorized, ToS-violating). Apify deferred until revenue. |
| LLM | Swappable OpenAI-compatible client. omniroute today; must be one config line to change. |
| Coupling | No dependency on hermes. omniroute is a URL, not an integration. |
| Audience geography | Undecided by design — the research stage scores it. |

## 3. Revenue model

Primary: YouTube ad revenue on an owned channel. Secondary, later: selling pipeline output as a service.

Milestones, per current YouTube policy:

- **Tier 1 (first money):** 500 subscribers + 3,000 watch hours (or 3M Shorts views) in 90 days. Unlocks Super Thanks, Memberships, Shopping. **This is the 90-day target.**
- **Tier 2 (ad revenue):** 1,000 subscribers + 4,000 watch hours in 12 months (or 10M Shorts views in 90 days).

Format economics justify the Shorts→long-form strategy: India Shorts RPM runs ₹5–30 against ₹50–200 for long-form, with finance/tech long-form reaching ₹80–250. The same English content aimed at US/UK professionals runs $2–4 RPM. Shorts buy subscribers; long-form monetizes them.

Threads pays creators nothing — no payout program exists as of 2026. It is a traffic source, not a revenue line.

## 4. The policy problem, and how the architecture answers it

YouTube's "inauthentic content" policy (renamed 2026-07-15) disqualifies two things this project would otherwise produce by default:

1. *"Mass-produced templates reused across multiple videos with the same structure and content patterns."*
2. *"Readings of other materials you did not create — text from websites read verbatim."*

At 1–2 hrs/week of approve-reject, the operator is not adding differentiation by hand. Therefore the pipeline must generate it structurally. Two mechanisms, both enforced in code:

- **Per-video narrative structure.** The generator selects a shape from several based on what the sources support — a contested claim becomes a tension piece, comparable data points become a ranking, a single primary document becomes an explainer. No two consecutive videos share a shape. There is no script template in this codebase.
- **Verbatim-overlap ceiling.** `script/validate.py` rejects any script whose overlap with any source exceeds a threshold. This is what keeps sourced content out of the "readings of other materials" bucket.

Separately, YouTube requires disclosing synthetic content that realistically depicts real people or events, enforced by a three-strike ladder ending in permanent YPP removal. TTS narration over licensed stock imagery is not believed to trigger this, but the publish stage carries an explicit disclosure flag, defaulting to set whenever imagery depicts a real person or event.

## 5. Architecture

Single Python package. Stages communicate through the **filesystem**: each reads one directory and writes another.

```
research/ → topics/ → sources/ → scripts/ → voice/ → visuals/ → renders/ → published/
```

This shape earns its place three ways: the approve/reject gate becomes "look in `scripts/pending/`" with no UI to build; every stage is independently runnable and testable, so a render bug never forces a re-scrape; and the pipeline is resumable, so a crash at render costs a render rather than a day of API quota.

No daemon, no message queue, no n8n. A CLI plus cron.

### Governing rule

**Provenance or nothing.** Every factual claim carries a source URL, an API response id, and a retrieval timestamp. A validator between stages rejects unprovenanced artifacts. There is no fallback-to-hardcoded path anywhere; when a source is unavailable the stage fails loudly and writes nothing.

This exists because the prior scaffolding's `research_niches.py` returned a canned topic list when its Apify key was missing, indistinguishable from scraped data. That failure mode must be structurally impossible.

## 6. Components

```
providers/                       thin API clients, every record provenanced
  youtube_api.py                 Data API v3 — search, videos, channels
  instagram_research.py          instagrapi. Throwaway account. ToS-violating.
  instagram_publish.py           Graph API. Real Business account. Never shares creds with the above.
  threads_publish.py             Official Threads API
  threads_research.py            NOT IMPLEMENTED until Apify. Absent = "not collected".
  llm.py                         OpenAI-compatible; base_url from config

research/
  discover.py                    candidate niches from seeds + YouTube search
  metrics.py                     competition density, view velocity, channel-age spread, cadence
  rpm_table.py                   RPM by niche × geography — checked-in data file, sourced per row
  score.py                       ranked report

sourcing/                        primary docs: full text + URL + retrieval timestamp
script/
  generate.py                    LLM from sources, structure chosen per video, inline citations
  validate.py                    THE POLICY GATE — see §4
voice/                           edge-tts → audio + word-level timings
visuals/                         Openverse / Wikimedia, license recorded per asset
render/                          ffmpeg; 16:9 long-form and 9:16 Short from shared material
publish/                         YouTube OAuth · IG Reels · Threads
review/                          approve/reject gate
provenance.py                    record type + validator, used by everything
```

### Credential separation (safety-critical)

`instagrapi` logs in as a real user and violates Meta's ToS; bans occur. If the scraping account were also the publishing account, one ban would cost both the research input and the distribution channel. The two Instagram modules therefore never share credentials, and this separation is not to be collapsed for convenience.

### `rpm_table.py`

RPM figures drive every ranking decision, and an LLM will invent them readily. So this is a checked-in data file with a source URL and date per row, updated by hand. Wrong-but-cited beats confident-and-fabricated.

## 7. Data flow

### Weekly research loop (cron)

```
pipeline research
  → YouTube Data API sweep + instagrapi research account
  → score = f(RPM × geography, competition density, view velocity, channel-age spread)
  → data/research/<date>/report.json + report.md
```

### Per-video loop

```
pipeline source  <topic>    primary docs
pipeline script  <topic>    generate + validate → scripts/pending/   ← operator gate
pipeline voice   <slug>     audio + word timings
pipeline visuals <slug>     assets + licenses
pipeline render  <slug>     16:9 long-form, 9:16 Short (≤90s, IG Reels compatible)
pipeline publish <slug>     YouTube · IG Reels · Threads
```

Each artifact directory carries `state.json` with stage and status, so any stage resumes without redoing its predecessor.

## 8. Quota budget

YouTube Data API free tier is 10,000 units/day. Costs are wildly uneven, and this dictates query design:

| Call | Units |
|---|---|
| `search.list` | 100 |
| `videos.list` | 1 |
| `channels.list` | 1 |
| `videos.insert` | 1,600 |

The scorer spends a small number of searches to find candidate channels, then fans out over cheap list calls for metrics — roughly 30 searches plus ~2,000 list calls per run, comfortably inside one day. A naive design burns the entire quota in 100 calls.

`videos.insert` at 1,600 units caps uploads at **6/day**, which matters only for bulk backfill.

Instagram/Threads publishing caps are 250 posts / 1,000 replies / 100 deletions per profile per 24h. Not a practical constraint.

## 9. Failure handling

Governing rule: **fail loudly, write nothing.** No stage emits partial or synthesised output when an input is missing.

- Quota exhaustion (`403 quotaExceeded`) stops the run cleanly and resumes next day. It never degrades to fewer samples, because a silently smaller sample produces a confidently wrong ranking.
- Rate limits: exponential backoff.
- Renders write to a temp path and move on success, so a crash cannot leave a half-video that looks finished.
- `instagrapi` login challenge or ban disables the research stage and alerts. It never falls back to cached or invented Instagram data, and never touches publishing credentials.

## 10. Testing

Concentrated where the money and the risk are.

- **`script/validate.py` gets adversarial tests.** Fabricated claims, claims citing a source that does not contain them, and near-verbatim lifts must all be rejected. This module stands between the project and demonetization; it is tested like security code.
- **Scorer math** unit-tested against hand-computed fixtures, including degenerate cases (zero competitors, missing RPM row).
- **Providers** tested against recorded fixtures. Never live APIs in CI — live calls burn quota and make tests flaky.
- **One end-to-end smoke test** rendering a 10-second video from fixtures, so the ffmpeg chain cannot silently rot.

Deliberately not tested heavily: LLM output quality. It is non-deterministic, and the validator already enforces the properties that matter.

## 11. Out of scope (YAGNI)

Cut from the prior scaffolding, all addable later, none needed to reach first revenue: n8n and its webhook workflows; the multi-provider TTS abstraction (edge-tts is free and adequate); income tracking; a web UI.

## 12. Lead-time actions

Meta App Review takes 2–4 weeks, with a separate submission per permission and a screencast of the full flow. It costs nothing but calendar time, so it starts immediately and in parallel with implementation.

- [ ] Convert Instagram account to **Business** (Creator accounts cannot publish via API)
- [ ] Create Meta developer app; link Facebook Page + IG Professional account
- [ ] Submit `instagram_business_basic` and `instagram_business_content_publish` for review
- [ ] Link Threads profile to the Instagram Professional account
- [ ] Create Google Cloud project, enable YouTube Data API v3, create OAuth credentials
- [ ] Create the throwaway Instagram account for research scraping

## 13. Build order

This design is too large for one implementation plan. It decomposes into four, each independently useful and each gated on the previous one working against real data.

**Plan 1 — research engine.** `provenance.py`, `providers/youtube_api.py`, `research/*`. Ends when `pipeline research` produces a ranked report whose every number traces to a real API response. Gate: the report has to be believable enough to pick a niche from. Nothing downstream is written until it is.

**Plan 2 — vertical slice to one published Short.** `sourcing/`, `script/` (including the validator), `voice/`, `visuals/`, `render/`, `publish/youtube.py`. One niche, one topic, one video, published. Deliberately narrow: proves the chain end to end and flushes out OAuth, ffmpeg and TTS timing, which are the fiddly integrations.

**Plan 3 — long-form and volume.** Long-form render path, the review gate CLI, cron scheduling, quota pacing.

**Plan 4 — multi-platform distribution.** `instagram_publish.py`, `threads_publish.py`. Gated on Meta App Review completing (§12), which is why it is last despite starting first in calendar terms.

`instagram_research.py` slots into Plan 1 or 3 depending on whether the throwaway account is ready. `threads_research.py` stays unbuilt until there is revenue to justify Apify.

## 14. Open questions

- Audience geography is deliberately unresolved; the first research run decides it.
- The verbatim-overlap threshold in `validate.py` needs an empirical value. Start strict, loosen only with evidence.
- Whether TTS narration alone triggers YouTube's synthetic-content disclosure requirement is not settled from public documentation. Default to disclosing when imagery depicts real people or events.

## Sources

- [YouTube inauthentic content policy](https://www.creatorhandbook.net/youtube-updates-monetization-policy-for-inauthentic-content/)
- [TechCrunch — YouTube clarifies AI slop policy](https://techcrunch.com/2026/07/20/youtube-clarifies-policies-around-ai-slop-and-upsetting-videos/)
- [YouTube Partner Program requirements 2026](https://vidiq.com/blog/post/youtube-partner-program-guide/)
- [India RPM by niche](https://www.identitykit.in/blog/youtube-rpm-india-niche-2026)
- [Threads API pricing](https://www.blotato.com/blog/threads-api-pricing)
- [Threads publishing API](https://postproxy.dev/blog/how-to-post-to-threads-via-api/)
- [Instagram Reels API publishing guide](https://postproxy.dev/blog/instagram-reels-api-publishing-guide/)
- [Instagram Graph API 2026](https://www.netrows.com/blog/instagram-graph-api-guide-2026)
