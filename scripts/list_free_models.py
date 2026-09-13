"""List currently-free chat models on OpenRouter (public endpoint, no key needed).

Prints id + name for models with prompt price 0, newest first. Use the output
to pick a working AI_MODEL value for .env.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

data = httpx.get("https://openrouter.ai/api/v1/models", timeout=60.0).json()
free = [
    model
    for model in data["data"]
    if model.get("pricing", {}).get("prompt") in ("0", "0.0", 0)
    and "text" in str(model.get("architecture", {}).get("modality", ""))
]
free.sort(key=lambda m: m.get("created", 0), reverse=True)
for model in free[:30]:
    print(model["id"], "|", model.get("name"))
print("total free text models:", len(free))
