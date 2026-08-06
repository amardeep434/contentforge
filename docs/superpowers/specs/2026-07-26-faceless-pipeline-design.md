# contentforge — Design

**Date:** 2026-07-26
**Status:** Approved, pending implementation plan — **partially invalidated 2026-07-29**

> **Check [claims-ledger.md](../../findings/claims-ledger.md) before acting on any
> claim in this document.** Evidence gathered on 2026-07-29 refuted several premises
> it was written on, including that asset polish drives views (C-011), that the
> "Every X Explained" format carries value on its own (C-010), and every channel
> ranking based on mean views-per-video (C-001). Sections not touched by those
> claims still stand.

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

⚠️ **Every RPM figure in this section is marketing-blog sourced and unverified**
(C-034). The only measured evidence available — two YouTube Studio screenshots —
computes to **$3.92 and $3.93 per 1,000 views** (C-040), below every US figure
quoted here. Treat these as directional at best; real RPM is knowable only from
our own Studio data.

Format economics justify the Shorts→long-form strategy: India Shorts RPM runs ₹5–30 against ₹50–200 for long-form, with finance/tech long-form reaching ₹80–250. The same English content aimed at US/UK professionals runs $2–4 RPM. Shorts buy subscribers; long-form monetizes them.

Threads pays creators nothing — no payout program exists as of 2026. It is a traffic source, not a revenue line.

## 4. The policy problem, and how the architecture answers it

YouTube's "inauthentic content" policy (renamed 2025-07-15) disqualifies two things this project would otherwise produce by default:

1. *"Mass-produced templates reused across multiple videos with the same structure and content patterns."*
2. *"Readings of other materials you did not create — text from websites read verbatim."*

At 1–2 hrs/week of approve-reject, the operator is not adding differentiation by hand. Therefore the pipeline must generate it structurally. Two mechanisms, both enforced in code:

- **Per-video narrative structure.** ⚠️ **Revised 2026-07-30.** This originally
  read "no two consecutive videos share a shape; there is no script template in
  this codebase." The evidence contradicts it: every channel measured runs a
  **rigid** template, and opening style is a channel-level constant rather than a
  per-video variable (C-027). Art History Explained uses the identical structure
  nine times for a 111,040 median. Deliberately varying structure would be
  copying the losers.
  What actually satisfies the policy is **per-video authored substance** — each
  video carrying research specific to its subject, not a name substituted into a
  frame (C-032). The template is the format; the substance is the differentiator.
  The generator therefore holds structure fixed and varies content.
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
  youtube_api.py                 Data API v3 — search, channels, playlistItems, videos
  instagram_research.py          instagrapi. Throwaway account. ToS-violating. (Plan 3)
  instagram_publish.py           Graph API. Real Business account. Never shares creds. (Plan 4)
  threads_publish.py             Official Threads API (Plan 4)
  threads_research.py            IMPLEMENTED 2026-07-30 — Jina Reader, no key, no
                                 quota. The assumption that this needed Apify or
                                 App Review was wrong for *reading* (C-038);
                                 publishing still needs the official API.
  reddit_research.py             OpenCLI browser bridge. Full post bodies and an
                                 engagement score (C-043).
  llm.py                         OpenAI-compatible; base_url from config (Plan 2)

research/
  leads.py                       gather claims + screenshots from a source
  analytics.py                   pure: measurements → verdict + reason
  potentials.py                  cumulative verified-channel list, keyed on id
  seen.py                        every lead and what became of it, across runs
  niches.py                      niche table (RPM figures unverified — C-034)
  discover.py / trajectory.py / changes.py / score.py / report.py
                                 the two failed research engines. Superseded by
                                 the lead loop; kept for the record (C-026).

sourcing/                        primary docs (Plan 2)
script/                          generation + provenance validator (Plan 2)
voice/ visuals/ render/          production (Plan 2/3)
publish/                         platform upload (Plan 2/4)
review/                          approve/reject gate (Plan 3)
provenance.py                    record type + validator, used by everything
```

## 7. Research method — SUPERSEDED

> **This approach was built twice and failed both times.** See
> `docs/findings/2026-07-26-research-engine-negative-result.md`. Revision 1's metrics were
> bounded by our own sample size; revision 2's velocity ratio is confounded by view
> front-loading — verified against a mature channel that scored a 3.0x "breakout" while its
> raw view counts were declining. Separating "this channel improved" from "this video is
> newer" needs per-video history at matched ages, which the API does not expose.
>
> Niche selection now falls back to RPM plus what the operator can sustain. The section is
> kept because the quota accounting and the client it describes are still in use.


The first version of this engine measured **states** — how big are the channels in a niche, how many are there. That failed: search returns the incumbents for every query, so competitor counts were bounded by our own sample size and every niche looked identically saturated. The ranking collapsed to an RPM lookup.

This version measures **transitions**. A channel's current size says little; the shape of its climb says a lot.

### The constraint

The YouTube API exposes **no historical channel data**. `channels.list` returns current subscriber and view counts only. There is no way to see when a channel crossed 1,000 subscribers.

### The workaround, which is better than the thing it replaces

Per-video data reconstructs the trajectory:

```
channels.list  part=contentDetails   → uploads playlist id
playlistItems.list                   → up to 50 video ids per call
videos.list                          → publishedAt, viewCount, duration, title
```

Each video is a dated observation. A channel whose recent videos vastly outperform its older ones has broken out, and the video where that begins is the inflection.

### Normalisation (non-negotiable)

Views accumulate with age. A two-year-old video has had two years to gather views; last week's has had six days. **All comparisons use views-per-day-since-publish**, never raw view counts. Getting this wrong inverts the entire analysis, making every old video look successful.

### Inflection detection

For each channel, compute views-per-day for every video, ordered by publish date. The inflection is the point maximising the ratio of median velocity after it to median velocity before it, subject to a minimum of five videos on each side. A channel with no such point above a threshold ratio has not broken out and is recorded as such — not discarded, because non-breakouts are the control group.

### Change attribution — within channel, not across

Comparing breakout channels to each other invites survivorship bias: "posted consistently then went viral" describes the winners and equally describes the thousands who did the same and sank.

So attribution is **within-channel**: for each channel with an inflection, diff its pre-inflection videos against its post-inflection videos on duration, upload cadence, title length and structure, and topic terms. Same creator, same baseline, so channel-level confounds cancel.

### What this cannot do

Stated here so the report never implies otherwise:

- **No causal claims.** Retention curves, traffic sources and thumbnail click-through are not exposed for other people's channels. We observe what changed around an inflection and that it coincided. We never observe why it worked.
- **Survivorship bias is reduced, not eliminated.** Search still surfaces channels that already won. Within-channel comparison controls for channel-level confounds, not for selection into the sample.
- **Sample is search-shaped.** Channels that never rank for a seed query are invisible regardless of merit.

## 8. Niche table

`data/niches.csv`, one hand-sourced row per niche/geography, extended from the RPM-only version:

| column | meaning |
|---|---|
| niche, geography | key |
| rpm_low, rpm_high, currency | revenue per 1,000 views |
| memberships_available | false where YouTube disables Super Thanks / Memberships |
| seed_queries | pipe-separated, long-tail rather than head terms |
| source_url, retrieved_at | provenance |

Roughly 12–15 categories: finance, tech, education, health, gaming, true crime, history, DIY, food, travel, self-improvement, business, science, kids, entertainment.

`memberships_available` exists because of Made for Kids. COPPA bars behavioural tracking on under-13 content, so only contextual ads serve (RPM $1–3 against $20–40 for finance), and **Super Thanks and Channel Memberships are disabled at platform level**. That removes the Tier 1 revenue path entirely, and YouTube's automated classifier applies the restriction retroactively to back catalogues. The scorer penalises restricted niches accordingly rather than the operator arguing about it — if kids still ranks well despite the penalty, it earns the slot on evidence.

**RPM sources disagree, and each row cites exactly one.** Published RPM figures vary materially between sources — tech is $15-25 in one and $8-15 in another. Each row therefore names the single source it came from rather than blending. The ranking is comparative, so a consistent bias across rows matters less than relative order; a source that systematically over-rates one niche would distort it, which is why rows are spread across five independent sources.

**Seed queries must be long-tail.** Head terms ("index funds", "ai tools") return the same incumbents for every niche, which is what defeated the first version. Narrow queries are where competitive structure actually varies.

## 9. Sampling scale and quota

Search is expensive; everything else is nearly free. This inverts the budget from the previous design.

| call | units | note |
|---|---|---|
| `search.list` | 100 | the only costly call |
| `channels.list` | 1 | ≤50 ids per call — 51 returns HTTP 400 `invalidFilters` |
| `playlistItems.list` | 1 | ≤50 videos per call |
| `videos.list` | 1 | ≤50 ids per call |

Per channel with a 50-video history: ~3 units. So a run sampling **500 channels** costs roughly:

```
20 searches            2,000
500 channels × 3       1,500
                       -----
                       3,500 of 10,000 units
```

Wide sampling is affordable; the previous design's narrowness was never a budget constraint, only a design error. Runs are capped by the ledger and stop cleanly rather than degrading to a smaller sample, because a silently truncated sample yields a confidently wrong ranking.

## 10. Scoring

```
score = rpm_usd
      × breakout_rate            fraction of sampled channels with a detected inflection
      × median_breakout_lift     median post/pre velocity ratio among those
      × membership_factor        1.0 normally, penalised where Tier 1 is unavailable
```

Rationale: RPM sets the ceiling. Breakout rate answers "do newcomers in this niche actually break through" — the question the old competitor-count metric was trying and failing to ask. Breakout lift answers "when they do, how big is the jump". Membership factor encodes whether first revenue is reachable at 500 subs or only at 1,000.

These weights remain a hypothesis. If a run ranks something obviously wrong, suspect the formula before the data.

## 11. Report rendering

The first version embedded all 50 channel ids in every provenance URL, producing ~3,000-character source links and an unreadable report. Fixed: markdown cites the response **etag** and links to the raw response stored under `data/research/<date>/raw/<etag>.json`. Full auditability, readable output.

## 12. Creator-claim verification, and the Threads path

The one research method that produced evidence today: take channels named in creator
marketing, and check each against the API.

**The asymmetry that makes it work.** View, subscriber and video counts are public and
retrievable for any channel. Revenue is exposed only to the channel owner. So a post
showing both can have half of it confirmed — and posts routinely format the two
identically, so an earnings figure computed as `views x assumed_RPM` reads as though it
were measured. Confirming views never confirms revenue.

Implemented as `pipeline verify @handle --claimed-views N --rpm R`. Handle lookup costs
**1 quota unit** against a search's 100. Implied earnings require an explicit `--rpm` and
are labelled as arithmetic. Workflow captured in `.claude/skills/verify-creator-claims/`.

### Threads access: browser now, API later

Reading Threads through the Chrome extension with the operator's logged-in session is a
**stopgap**, not the design. It does not scale, it cannot be scheduled, and automating
collection at volume through it would violate Meta's ToS.

The destination is the official Threads API, which does support this:

- `GET /keyword_search` with a keyword, or `search_mode=TAG` for topic tags — the tag feed
  is exactly what was browsed manually (`serp_type=tags`).
- Requires `threads_basic` plus `threads_keyword_search`.
- **Without App Review approval the endpoint returns only the authenticated user's own
  posts.** Public-post search requires advanced access, and may additionally require
  business verification.
- Free; no paid tier.

This adds two permissions to the same App Review submission as the Instagram publishing
scopes (§16). Submitting them together saves a review cycle, so the Threads permissions
should go in now even though the consumer is built later.

`providers/threads_research.py` stays unimplemented until that approval lands. Until then
the browser workflow is operator-driven and manual, and the research report records
"Threads: not collected" rather than implying coverage.

## 13. Failure handling

Governing rule: **fail loudly, write nothing.** No stage emits partial or synthesised output when an input is missing.

- Quota exhaustion (`403 quotaExceeded`) stops the run cleanly and resumes next day. It never degrades to fewer samples, because a silently smaller sample produces a confidently wrong ranking.
- Rate limits: exponential backoff.
- Renders write to a temp path and move on success, so a crash cannot leave a half-video that looks finished.
- `instagrapi` login challenge or ban disables the research stage and alerts. It never falls back to cached or invented Instagram data, and never touches publishing credentials.

## 14. Testing

Concentrated where the money and the risk are.

- **`script/validate.py` gets adversarial tests.** Fabricated claims, claims citing a source that does not contain them, and near-verbatim lifts must all be rejected. This module stands between the project and demonetization; it is tested like security code.
- **Scorer math** unit-tested against hand-computed fixtures, including degenerate cases (zero competitors, missing RPM row).
- **Providers** tested against recorded fixtures. Never live APIs in CI — live calls burn quota and make tests flaky.
- **One end-to-end smoke test** rendering a 10-second video from fixtures, so the ffmpeg chain cannot silently rot.

Deliberately not tested heavily: LLM output quality. It is non-deterministic, and the validator already enforces the properties that matter.

## 15. Out of scope (YAGNI)

Cut from the prior scaffolding, all addable later, none needed to reach first revenue: n8n and its webhook workflows; the multi-provider TTS abstraction (edge-tts is free and adequate); income tracking; a web UI.

## 16. Lead-time actions

Meta App Review takes 2–4 weeks, with a separate submission per permission and a screencast of the full flow. It costs nothing but calendar time, so it starts immediately and in parallel with implementation.

- [ ] Convert Instagram account to **Business** (Creator accounts cannot publish via API)
- [ ] Create Meta developer app; link Facebook Page + IG Professional account
- [ ] Submit `instagram_business_basic` and `instagram_business_content_publish` for review
- [ ] In the **same** submission, request `threads_basic` and `threads_keyword_search`
      (advanced access — without it, keyword search returns only your own posts)
- [ ] Complete business verification if Meta requires it for advanced access
- [ ] Link Threads profile to the Instagram Professional account
- [ ] Create Google Cloud project, enable YouTube Data API v3, create OAuth credentials
- [ ] Create the throwaway Instagram account for research scraping

## 17. Build order

This design is too large for one implementation plan. It decomposes into four, each independently useful and each gated on the previous one working against real data.

**Plan 1 — research engine.** `provenance.py`, `providers/youtube_api.py`, `research/*`. Ends when `pipeline research` produces a ranked report whose every number traces to a real API response. Gate: **if the top-ranked niche is one the operator could have guessed without building this, the engine has told them nothing and needs rework.** Nothing downstream is written until it clears.

**Both revisions of Plan 1 were built, run against live data, and failed that gate.** Revision 1's competitor count and entrability were bounded by our own sample size; revision 2's velocity ratio is confounded by view front-loading. Niche selection now falls back to RPM plus what the operator can sustain — see §7 and `docs/findings/2026-07-26-research-engine-negative-result.md`. What survives Plan 1 is the provenance core, the quota ledger, the YouTube client, the niche table and `pipeline verify` (§12).

**Plan 2 — vertical slice to one published video. Revised toward fewer, better.**
`sourcing/`, `script/` (including the validator), `voice/`, `visuals/`, `render/`,
`publish/youtube.py`. One niche, one topic, one video, published.

The original plan assumed volume — 3-5 long-form plus 10-15 Shorts per month. The verified
data contradicts that:

```
Explained in minutes    2 videos →  2,475,477 views   1,237,739 views/video   110,000 subs in 5 months
Family Life English    42 videos → 11,443,658 views     272,468 views/video    42 uploads in 44 days
ENEM                   28 videos →  4,674,845 views     166,959 views/video
American Legends      193 videos → 14,350,373 views      74,354 views/video
Its Just Cars!        142 videos →  6,132,088 views      43,184 views/video    17,100 subs in 16 months
```

A 28x spread in output efficiency across the same faceless format, on five different topics.
Topic does not explain it.

**Cadence does not explain it either, and an earlier draft of this section claimed it did.**
That draft read "volume is the least efficient strategy" off the four channels available at the
time. Family Life English breaks it: the highest upload rate in the sample — daily — while
ranking *second* in views-per-video. Cadence and per-video performance are independent.

So Plan 2 optimises per-video quality, not throughput — and specifically **not** scarcity for
its own sake:

- **First milestone is three videos, not thirty** — because three is the smallest number that
  teaches you anything from retention data, not because fewer is inherently better. Volume
  scales later if the format proves repeatable at quality, as Family Life English demonstrates
  it can.
- **Measure before producing more.** Publish, read retention and traffic source from your
  own Analytics, then decide the next one. That is the feedback loop no amount of public
  data could provide.
- **The pipeline is a quality instrument, not a factory.** Throughput features (batching,
  scheduling, queue management) move to Plan 3 or get cut.

Second-order effect worth stating: at three videos a month the operator can afford to
actually edit each script, which was ruled out under the volume plan at 1-2 hrs/week. That
substantially reduces the policy risk flagged in §4 — the differentiation no longer has to
come entirely from `validate.py`.

**Plan 3 — long-form and volume.** Long-form render path, the review gate CLI, cron scheduling, quota pacing.

**Plan 4 — multi-platform distribution.** `instagram_publish.py`, `threads_publish.py`. Gated on Meta App Review completing (§16), which is why it is last despite starting first in calendar terms. The same submission carries the Threads keyword-search permissions that replace the manual browser workflow (§12).

`instagram_research.py` slots into Plan 1 or 3 depending on whether the throwaway account is ready. `threads_research.py` stays unbuilt until there is revenue to justify Apify.

## 18. Open questions

- Audience geography is deliberately unresolved; the research run decides it.
- The breakout-detection threshold ratio and the minimum videos either side of an inflection need empirical values. Start strict.
- Whether within-channel change attribution actually discriminates is itself the open question revision 2 exists to answer. If breakout rate proves as flat across niches as competitor count was, the premise that public metrics can identify a niche is wrong, and niche selection should fall back to RPM plus operator interest.
- The verbatim-overlap threshold in `validate.py` needs an empirical value. Start strict, loosen only with evidence.
- Whether TTS narration alone triggers YouTube's synthetic-content disclosure requirement is not settled from public documentation. Default to disclosing when imagery depicts real people or events.

## Sources

- [YouTube inauthentic content policy](https://www.creatorhandbook.net/youtube-updates-monetization-policy-for-inauthentic-content/)
- [TechCrunch — YouTube clarifies AI slop policy](https://techcrunch.com/2026/07/20/youtube-clarifies-policies-around-ai-slop-and-upsetting-videos/)
- [YouTube Partner Program requirements 2026](https://vidiq.com/blog/post/youtube-partner-program-guide/)
- [India RPM by niche](https://www.identitykit.in/blog/youtube-rpm-india-niche-2026)
- [COPPA cuts kids-channel revenue by up to 80%](https://www.techtimes.com/articles/320340/20260713/ai-kids-cartoon-gold-rush-has-hidden-tax-coppa-cuts-revenue-80.htm)
- [Made for Kids monetization rules](https://vidiq.com/blog/post/make-money-kids-youtube-channel/)
- [YouTube Made for Kids ad restrictions 2026](https://www.auditsocials.com/blog/youtube-made-for-kids-ad-restrictions-update-2026-coppa-expansion-limited-ads-mode-family-friendly-compliance)
- [Threads API pricing](https://www.blotato.com/blog/threads-api-pricing)
- [Threads publishing API](https://postproxy.dev/blog/how-to-post-to-threads-via-api/)
- [Instagram Reels API publishing guide](https://postproxy.dev/blog/instagram-reels-api-publishing-guide/)
- [Instagram Graph API 2026](https://www.netrows.com/blog/instagram-graph-api-guide-2026)
- [Threads Keyword Search API](https://developers.facebook.com/docs/threads/keyword-search/)
- [Threads keyword and topic tag search](https://developers.facebook.com/documentation/threads/keyword-search)
