"""Busy main model -> the run restarts on the fallback model; other errors are not hidden by the fallback."""
import asyncio
import json

import httpx
import pytest

from app.ai import openai_compat
from app.ai.openai_compat import Client, ProviderError, run


def _client(handler) -> Client:
    c = Client("http://ai.test/", "k")
    c._http = httpx.AsyncClient(base_url="http://ai.test/", transport=httpx.MockTransport(handler))
    return c


def _answer(text: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                                     "usage": {"prompt_tokens": 3, "completion_tokens": 2}})


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def instant(_s):
        return None
    monkeypatch.setattr(openai_compat.asyncio, "sleep", instant)


def _go(client, **kw):
    return asyncio.run(run(client, model="main", system="s", history=[{"role": "user", "content": "hi"}], tools=[],
                           max_iterations=3, max_tokens=100, **kw))


def test_busy_main_model_switches_to_fallback():
    calls, reset = [], []

    def handler(req):
        m = json.loads(req.content)["model"]
        calls.append(m)
        return httpx.Response(503, json={"error": {"message": "high demand"}}) if m == "main" else _answer("from lite")

    out = _go(_client(handler), fallback_model="lite", on_fallback=lambda: reset.append(1))
    assert out["model"] == "lite" and out["text"] == "from lite"
    assert calls == ["main", "main", "main", "lite"]          # 3 quick tries, then the fallback
    assert reset == [1]                                       # caller told to drop partial results


def test_main_model_used_when_available():
    out = _go(_client(lambda req: _answer("from main")), fallback_model="lite")
    assert out["model"] == "main" and out["text"] == "from main"


def test_non_busy_error_is_not_masked():
    def handler(req):
        return httpx.Response(401, json={"error": {"message": "bad key"}})
    with pytest.raises(ProviderError) as e:
        _go(_client(handler), fallback_model="lite")
    assert e.value.status == 401


def test_no_fallback_keeps_full_retries():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503, json={"error": {"message": "busy"}})
    with pytest.raises(ProviderError):
        _go(_client(handler))
    assert len(calls) == 6
