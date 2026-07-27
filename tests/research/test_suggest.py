import json
from unittest.mock import patch

from contentforge.research.suggest import suggest

PAYLOAD = json.dumps(
    ["index funds", ["index funds", "index funds vs etf",
                     "index funds for beginners in tamil"], [], {}]
).encode()


class _Response:
    def read(self): return PAYLOAD
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_filters_head_terms_and_keeps_long_tail():
    with patch("urllib.request.urlopen", return_value=_Response()):
        assert suggest("index funds") == [
            "index funds vs etf", "index funds for beginners in tamil"
        ]
