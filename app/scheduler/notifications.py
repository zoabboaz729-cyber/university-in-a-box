"""Web Push helpers for user opt-in notifications."""
import base64
import json
import os
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from py_vapid import Vapid02
from pywebpush import webpush

from app.db import get_connection


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _decode_vapid_public(public_key: str | None) -> str:
    if not public_key:
        return ""
    try:
        raw = base64.urlsafe_b64decode(public_key + "=" * (-len(public_key) % 4))
        if len(raw) == 65 and raw[0] == 0x04:
            return _b64url_encode(raw[1:])
        return public_key
    except Exception:
        return ""


def _ensure_vapid_keys() -> tuple[str, str]:
    public_key = os.environ.get("APP_VAPID_PUBLIC_KEY", "").strip()
    private_key = os.environ.get("APP_VAPID_PRIVATE_KEY", "").strip()
    if public_key and private_key:
        return public_key, private_key

    vapid = Vapid02()
    vapid.generate_keys()
    public_bytes = vapid.public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    public_key = _b64url_encode(public_bytes[1:])
    private_key = vapid.private_pem().decode("utf-8")
    os.environ["APP_VAPID_PUBLIC_KEY"] = public_key
    os.environ["APP_VAPID_PRIVATE_KEY"] = private_key
    return public_key, private_key


def get_vapid_public_key() -> str:
    return _ensure_vapid_keys()[0]


def get_vapid_private_key() -> str:
    return _ensure_vapid_keys()[1]


def save_push_subscription(user_id: int, endpoint: str, p256dh: str, auth: str,
                          enabled: bool = True) -> bool:
    if not user_id or not endpoint or not p256dh or not auth:
        return False
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, enabled) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(endpoint) DO UPDATE SET "
            "user_id=excluded.user_id, p256dh=excluded.p256dh, auth=excluded.auth, "
            "enabled=excluded.enabled",
            (user_id, endpoint, p256dh, auth, int(enabled)),
        )
        return True


def set_push_subscription_enabled(user_id: int, endpoint: str, enabled: bool) -> bool:
    with get_connection() as conn:
        rowcount = conn.execute(
            "UPDATE push_subscriptions SET enabled = ? WHERE user_id = ? AND endpoint = ?",
            (int(enabled), user_id, endpoint),
        ).rowcount
        return rowcount > 0


def delete_push_subscription(user_id: int, endpoint: str | None = None) -> bool:
    with get_connection() as conn:
        if endpoint:
            rowcount = conn.execute(
                "DELETE FROM push_subscriptions WHERE user_id = ? AND endpoint = ?",
                (user_id, endpoint),
            ).rowcount
            return rowcount > 0
        rowcount = conn.execute(
            "DELETE FROM push_subscriptions WHERE user_id = ?",
            (user_id,),
        ).rowcount
        return rowcount > 0


def list_push_subscriptions(user_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT endpoint, p256dh, auth, enabled FROM push_subscriptions "
            "WHERE user_id = ? AND enabled = 1 ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def has_push_subscription(user_id: int) -> bool:
    return bool(list_push_subscriptions(user_id))


def record_push_event(user_id: int, event_type: str, event_key: str) -> bool:
    if not user_id or not event_type or not event_key:
        return False
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO push_events (user_id, event_type, event_key) "
            "VALUES (?, ?, ?)",
            (user_id, event_type, event_key),
        )
        return cursor.rowcount > 0


def send_push_notification(user_id: int, title: str, body: str, url: str = "/",
                          dedupe_key: str | None = None) -> bool:
    """Send a browser push notification to every active subscription for `user_id`."""
    if not user_id:
        return False
    if dedupe_key:
        if not record_push_event(user_id, "notification", dedupe_key):
            return False
    subs = list_push_subscriptions(user_id)
    if not subs:
        return False
    key = get_vapid_private_key()
    if not key:
        return False
    claims = {
        "sub": "mailto:hello@university-in-a-box.local",
        "aud": "https://fcm.googleapis.com",
    }
    payload = {
        "title": title,
        "body": body,
        "icon": "/static/icons/icon-192.svg",
        "badge": "/static/icons/icon-192.svg",
        "url": url,
    }
    sent = False
    vapid_key = Vapid02.from_pem(key.encode("utf-8"))
    for sub in subs:
        payload_data = json.dumps(payload)
        try:
            webpush(
                {
                    "endpoint": sub["endpoint"],
                    "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
                },
                data=payload_data,
                vapid_private_key=vapid_key,
                vapid_claims=claims,
                ttl=600,
            )
            sent = True
        except Exception:
            continue
    return sent
