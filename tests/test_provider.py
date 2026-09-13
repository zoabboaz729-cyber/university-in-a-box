"""Phase 1a tests for the real provider adapter — HTTP mocked, no key needed.

Covers: posts to BASE_URL/chat/completions with model + messages and Bearer
auth; strips whitespace; raises ProviderError (after one retry) on HTTP
failure, malformed JSON shape, and empty content; raises ProviderError
immediately for missing key without touching the network.
"""
import httpx
import pytest

from app.ai.config import AIConfig
from app.ai.provider import OpenAICompatibleProvider, ProviderError


def make_provider(**overrides):
    values = {
        "provider": "openai_compatible",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "cohere/north-mini-code:free",
        "api_key": "test-key",
    }
    values.update(overrides)
    return OpenAICompatibleProvider(AIConfig(**values))


def fake_response(payload, status=200):
    request = httpx.Request("POST", "https://x.test/chat/completions")
    return httpx.Response(status, json=payload, request=request)


def good_payload(text="  hello  "):
    return {"choices": [{"message": {"content": text}}]}


def test_posts_correct_shape_with_bearer_auth(monkeypatch):
    calls = {}

    def capture(url, json=None, headers=None, timeout=None):
        calls.update({"url": url, "json": json, "headers": headers})
        request = httpx.Request("POST", url)
        return httpx.Response(200, json=good_payload(), request=request)

    monkeypatch.setattr(httpx, "post", capture)
    result = make_provider().generate("sys", "user")
    assert result == "hello"
    assert calls["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert calls["json"]["model"] == "cohere/north-mini-code:free"
    assert calls["json"]["messages"][0] == {"role": "system", "content": "sys"}
    assert calls["headers"]["Authorization"] == "Bearer test-key"


def test_retries_once_then_raises_on_http_error(monkeypatch):
    calls = {"n": 0}

    def failing(url, json=None, headers=None, timeout=None):
        calls["n"] += 1
        request = httpx.Request("POST", url)
        return httpx.Response(500, json={"error": "boom"}, request=request)

    monkeypatch.setattr(httpx, "post", failing)
    with pytest.raises(ProviderError):
        make_provider().generate("sys", "user")
    assert calls["n"] == 2


def test_raises_on_malformed_and_empty(monkeypatch):
    request = httpx.Request("POST", "https://x.test/chat/completions")
    for payload in ({"nope": 1}, {"choices": []}, {"choices": [{"message": {}}]}):
        monkeypatch.setattr(
            httpx, "post", lambda *a, **k: httpx.Response(200, json=payload, request=request)
        )
        with pytest.raises(ProviderError):
            make_provider().generate("sys", "user")
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *a, **k: httpx.Response(200, json=good_payload("   "), request=request),
    )
    with pytest.raises(ProviderError):
        make_provider().generate("sys", "user")


def test_http_error_includes_api_body(monkeypatch):
    # A 404 whose body says "model unavailable for free" must surface that
    # text — otherwise the user can't tell a dead model slug from a dead key.
    request = httpx.Request("POST", "https://x.test/chat/completions")
    body = '{"error": {"message": "This model is unavailable for free."}}'
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *a, **k: httpx.Response(404, text=body, request=request),
    )
    with pytest.raises(ProviderError) as exc_info:
        make_provider().generate("sys", "user")
    assert "unavailable for free" in str(exc_info.value)


def test_missing_key_raises_without_network(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("should not touch the network")

    monkeypatch.setattr(httpx, "post", boom)
    with pytest.raises(ProviderError):
        make_provider(api_key="").generate("sys", "user")
