"""OpenAI-compatible chat client.

base_url is a config value, not an integration. Points at omniroute today;
changing provider is one environment variable.
"""

import json
import urllib.request
from typing import Callable

from contentforge.errors import MissingDataError

Transport = Callable[[str, dict, dict], dict]


def http_transport(url: str, payload: dict, headers: dict) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


class LLMClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        transport: Transport = http_transport,
    ) -> None:
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._model = model
        self._transport = transport

    def complete(self, system: str, user: str, max_tokens: int = 4000) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "stream": False,
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        body = self._transport(self._url, payload, headers)
        choices = body.get("choices") or []
        if not choices:
            raise MissingDataError(f"LLM returned no choices: {str(body)[:200]}")
        content = choices[0].get("message", {}).get("content")
        if not content:
            raise MissingDataError("LLM returned an empty message")
        return content
