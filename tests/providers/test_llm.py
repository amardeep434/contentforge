import pytest

from contentforge.errors import MissingDataError
from contentforge.providers.llm import LLMClient


def transport_returning(text):
    def _transport(url, payload, headers):
        return {"choices": [{"message": {"content": text}}]}
    return _transport


def test_complete_returns_message_content():
    assert LLMClient("http://x/v1", "", "m", transport_returning("hello")).complete("s", "u") == "hello"


def test_sends_system_and_user_messages():
    seen = {}

    def _transport(url, payload, headers):
        seen.update(payload)
        return {"choices": [{"message": {"content": "ok"}}]}

    LLMClient("http://x/v1", "", "m", _transport).complete("SYS", "USER")
    assert [m["role"] for m in seen["messages"]] == ["system", "user"]
    assert seen["messages"][0]["content"] == "SYS"
    assert seen["model"] == "m"


def test_empty_response_raises_rather_than_returning_blank():
    with pytest.raises(MissingDataError):
        LLMClient("http://x/v1", "", "m", lambda u, p, h: {"choices": []}).complete("s", "u")


def test_api_key_goes_in_the_header_not_the_payload():
    seen = {}

    def _transport(url, payload, headers):
        seen["headers"], seen["payload"] = headers, payload
        return {"choices": [{"message": {"content": "ok"}}]}

    LLMClient("http://x/v1", "secret", "m", _transport).complete("s", "u")
    assert seen["headers"]["Authorization"] == "Bearer secret"
    assert "secret" not in str(seen["payload"])
