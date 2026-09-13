"""Manual smoke test: one REAL OpenRouter call (Phase 1a verification).

NOT part of the automated suite — run by the owner only, with their own key:
    copy .env.example .env   (paste AI_API_KEY into .env first)
    python scripts/smoke_provider.py
Reads .env via app.ai.config, sends one tiny prompt, prints the reply.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai.config import load_config  # noqa: E402
from app.ai.provider import ProviderError, get_provider  # noqa: E402


def main() -> int:
    config = load_config()
    print("base_url:", config.base_url)
    print("model:", config.model)
    print("key present:", bool(config.api_key))
    try:
        reply = get_provider().generate(
            "Reply with exactly the word PONG and nothing else.",
            "PING",
        )
    except ProviderError as exc:
        print("FAILED:", exc)
        return 1
    print("reply:", reply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
