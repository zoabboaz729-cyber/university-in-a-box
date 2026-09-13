"""Reads AI provider settings from the environment / .env file.

Phase 0: values are read but only the stub provider exists, so no real key
is needed yet. Uses only the standard library (tiny KEY=VALUE parser) so
Phase 0 needs no extra dependency for this.
"""
import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    """Load repo-root .env into os.environ without overwriting real env vars."""
    env_file = Path(__file__).resolve().parent.parent.parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


@dataclass
class AIConfig:
    provider: str
    base_url: str
    model: str
    api_key: str


def load_config() -> AIConfig:
    _load_dotenv()
    return AIConfig(
        provider=os.environ.get("AI_PROVIDER", "stub"),
        base_url=os.environ.get("AI_BASE_URL", ""),
        model=os.environ.get("AI_MODEL", ""),
        api_key=os.environ.get("AI_API_KEY", ""),
    )
