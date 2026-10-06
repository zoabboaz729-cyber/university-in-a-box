import os

from app.ai.config import load_config
from app.auth.store import increment_user_ai_quota

DEFAULT_MAX_FREE_QUOTA = 10


class QuotaExceeded(RuntimeError):
    """Raised when a user has no BYOK key and has exhausted the free quota."""


def max_free_quota() -> int:
    try:
        return max(0, int(os.environ.get("MAX_FREE_QUOTA", DEFAULT_MAX_FREE_QUOTA)))
    except (TypeError, ValueError):
        return DEFAULT_MAX_FREE_QUOTA


def resolve_ai_key_for_user(user: dict | None) -> tuple[str, str]:
    """Return (api_key, source) where source is 'byok' or 'server'.

    If a user has a stored BYOK key, decrypt it and use it. Otherwise, the
    server-owned key may be used up to the configured free quota. If the quota
    is exhausted, raise a friendly QuotaExceeded message.
    """
    if user and user.get("encrypted_ai_key"):
        from app.auth.security import decrypt_api_key

        key = decrypt_api_key(user["encrypted_ai_key"])
        if key:
            return key, "byok"

    cfg = load_config()
    key = (cfg.api_key or "").strip()
    if not key:
        raise QuotaExceeded(
            "No AI key is configured. Add a personal key in Settings or set AI_API_KEY."
        )

    if user is None or user.get("id") is None:
        return key, "server"

    used = int(user.get("ai_quota_used") or 0)
    if used >= max_free_quota():
        raise QuotaExceeded(
            "Your free AI quota is exhausted. Add your own API key in Settings to continue."
        )

    increment_user_ai_quota(user["id"])
    return key, "server"
