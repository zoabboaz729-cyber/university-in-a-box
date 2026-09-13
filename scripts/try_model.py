"""Try one model slug with a PING/PONG call. Usage: python scripts/try_model.py <slug>.

Prints HTTP status + reply or API error body. Reads base_url/key from .env,
overrides only the model.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from app.ai.config import load_config  # noqa: E402

slug = sys.argv[1]
config = load_config()
response = httpx.post(
    config.base_url.rstrip("/") + "/chat/completions",
    json={"model": slug, "messages": [{"role": "user", "content": "Reply PONG."}]},
    headers={"Authorization": "Bearer " + config.api_key},
    timeout=60.0,
)
print("model:", slug)
print("HTTP status:", response.status_code)
print("body:", response.text[:300])
