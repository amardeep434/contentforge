"""YouTube Data API quota accounting.

The free tier allows 10,000 units/day and costs are wildly uneven — a single
search.list costs as much as 100 channels.list calls. The ledger is immutable:
charge() returns a new ledger, so a caller can never accidentally spend units
by holding a stale reference.
"""

from dataclasses import dataclass, replace

from contentforge.errors import QuotaExceededError

UNIT_COSTS: dict[str, int] = {
    "search.list": 100,
    "videos.list": 1,
    "playlistItems.list": 1,
    "channels.list": 1,
    "videos.insert": 1600,
}


@dataclass(frozen=True)
class QuotaLedger:
    daily_limit: int = 10_000
    spent: int = 0

    @property
    def remaining(self) -> int:
        return self.daily_limit - self.spent

    def would_exceed(self, endpoint: str) -> bool:
        """True if charging endpoint would breach the limit. Does not charge."""
        return self.spent + UNIT_COSTS[endpoint] > self.daily_limit

    def charge(self, endpoint: str) -> "QuotaLedger":
        """Return a new ledger with endpoint's cost added.

        An unknown endpoint raises KeyError deliberately — silently assuming a
        zero cost would let an unbudgeted call slip past the ceiling.
        """
        cost = UNIT_COSTS[endpoint]
        if self.spent + cost > self.daily_limit:
            raise QuotaExceededError(
                f"{endpoint} costs {cost}; only {self.remaining} units remain"
            )
        return replace(self, spent=self.spent + cost)
