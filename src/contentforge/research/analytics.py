"""Decide what a measurement means, and say why.

This module is deliberately pure: measurements in, verdicts out, no network, no
files, no clock. That is the whole point of splitting it from resolution.
Criteria have already changed four times in this project - mean, then median,
then hit-rate, then reachability - and each change previously forced a full
rescan at ~2 quota units per channel. Judging stored measurements instead means
re-deciding costs nothing.

Every verdict carries the ruleset that produced it, so a potentials file written
under old criteria is recognisable rather than silently mixed in.
"""

from dataclasses import dataclass

#: Bump whenever a threshold below changes. Rows judged under an older version
#: can then be re-analysed rather than trusted.
CRITERIA_VERSION = "2026-07-30.1"

#: A channel needs enough videos before a median means anything. Three separate
#: conclusions in this project died from being read off n=4 (C-004/C-007/C-014).
MIN_VIDEOS = 8

#: mean/median. Above this the average is measuring one or two viral hits rather
#: than the channel's typical output (C-001).
MAX_SKEW = 3.0

#: Share of videos clearing the hit threshold. Below this the channel depends on
#: occasional luck; only ~5% of channels clear it (C-020).
MIN_HIT_RATE = 40.0

#: Above this, a channel's views come partly from its existing base and standing,
#: so its numbers say nothing about a channel starting from zero. Inferring from
#: large channels is the error C-007 was withdrawn for.
REACHABLE_MAX_SUBS = 80_000

EXEMPLAR = "exemplar"
WATCH = "watch"
REJECT = "reject"


@dataclass(frozen=True)
class Verdict:
    channel_id: str
    status: str
    reason: str
    criteria_version: str = CRITERIA_VERSION


def judge(measurement: dict) -> Verdict:
    """One channel's verdict, with the reason stated in the measurement's terms.

    Order matters: the first failing test is the one reported, so the reason is
    the most fundamental problem rather than an arbitrary one.
    """
    channel_id = measurement["channel_id"]
    n = int(measurement["n"])
    skew = float(measurement["skew"])
    hit_rate = float(measurement["hit_rate"])
    subs = int(measurement["subs"])
    median = int(measurement["median"])

    def verdict(status: str, reason: str) -> Verdict:
        return Verdict(channel_id, status, reason, CRITERIA_VERSION)

    if n < MIN_VIDEOS:
        return verdict(REJECT, f"only {n} long-form videos; need {MIN_VIDEOS} to judge")
    if skew > MAX_SKEW:
        return verdict(
            REJECT,
            f"lottery-shaped: mean is {skew:.1f}x the median, above {MAX_SKEW}",
        )
    if hit_rate < MIN_HIT_RATE:
        return verdict(
            REJECT,
            f"hit-rate {hit_rate:.0f}% is below {MIN_HIT_RATE:.0f}%",
        )
    if subs > REACHABLE_MAX_SUBS:
        return verdict(
            WATCH,
            f"repeatable, but {subs:,} subs is above {REACHABLE_MAX_SUBS:,} - its "
            "numbers cannot be extrapolated to a new channel",
        )
    ratio = median / max(subs, 1)
    return verdict(
        EXEMPLAR,
        f"repeatable and reachable: {subs:,} subs, median {median:,} "
        f"({ratio:.1f} views per subscriber), skew {skew:.1f}, hit-rate {hit_rate:.0f}%",
    )


def judge_all(measurements: list[dict]) -> list[Verdict]:
    return [judge(measurement) for measurement in measurements]


def tally(verdicts: list[Verdict]) -> dict[str, int]:
    counts = {EXEMPLAR: 0, WATCH: 0, REJECT: 0}
    for verdict in verdicts:
        counts[verdict.status] = counts.get(verdict.status, 0) + 1
    return counts
