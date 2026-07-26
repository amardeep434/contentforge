"""Seed configuration.

These niches and queries are a starting hypothesis. The scorer's job is to tell
you whether they are worth pursuing — treat the first report as a hypothesis
test, not an answer.
"""

NICHE_QUERIES: dict[str, list[str]] = {
    "finance": ["index funds", "personal finance tips", "etf investing"],
    "tech": ["ai tools", "coding tutorial", "software review"],
    "education": ["study techniques", "online courses", "skill building"],
}

DEFAULT_GEOGRAPHY = "US"
