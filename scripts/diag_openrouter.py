"""Diagnostic: load .env exactly like the app does and print SAFE metadata only.

Prints: whether .env exists, each AI_* value's presence/length, key prefix
(first 10 chars) and length — NEVER the full key. Then makes the real call
and prints the FULL response body on error (status + first 500 chars), so a
404 vs 401 vs bad-model-slug can be told apart.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from app.ai.config import load_config  # noqa: E402
from app.ai.provider import get_provider  # noqa: E402

env_file = Path(__file__).resolve().parent.parent / ".env"
print(".env exists:", env_file.exists())

config = load_config()
print("provider:", repr(config.provider))
print("base_url:", repr(config.base_url))
print("model:", repr(config.model))
print("key length:", len(config.api_key))
print("key prefix:", repr(config.api_key[:10]))
print("key has whitespace/newline:", any(c in config.api_key for c in " \n\r\t"))

# Raw call with full error body (provider.py discards the body on 4xx).
url = config.base_url.rstrip("/") + "/chat/completions"
try:
    response = httpx.post(
        url,
        json={
            "model": config.model,
            "messages": [{"role": "user", "content": "Reply PONG."}],
        },
        headers={"Authorization": "Bearer " + config.api_key},
        timeout=60.0,
    )
    print("HTTP status:", response.status_code)
    print("body:", response.text[:500])
except Exception as exc:
    print("transport error:", exc)
