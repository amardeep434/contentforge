"""Long-tail seed queries from YouTube autocomplete.

Free, unauthenticated, and outside the Data API quota. This is the same source
paid keyword tools resell, and it fixes the input we were hand-authoring:
head terms return the same incumbents for every niche, which is what defeated
the first research engine.
"""

import json
import urllib.parse
import urllib.request

ENDPOINT = "https://suggestqueries.google.com/complete/search"
MIN_WORDS = 3


def suggest(seed: str, min_words: int = MIN_WORDS, timeout: int = 10) -> list[str]:
    """YouTube's own autocomplete for `seed`, filtered to long-tail phrases."""
    query = urllib.parse.urlencode({"client": "firefox", "ds": "yt", "q": seed})
    with urllib.request.urlopen(f"{ENDPOINT}?{query}", timeout=timeout) as response:
        _term, suggestions, *_rest = json.loads(response.read().decode("utf-8"))
    return [s for s in suggestions if len(s.split()) >= min_words]
