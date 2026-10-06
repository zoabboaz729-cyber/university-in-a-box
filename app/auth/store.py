"""User persistence and query functions for authentication.
"""
from typing import Optional, Dict, Any
from app.db import get_connection


def create_user(email: str, password_hash: str, name: str) -> Dict[str, Any]:
    """Insert a new user record and return user dictionary.

    Email is normalized to lowercase and must be unique; a duplicate raises
    ValueError (checked here so both SQLite and PostgreSQL behave the same).
    """
    clean_email = email.strip().lower()
    clean_name = name.strip()
    if not clean_email:
        raise ValueError("Email is required.")
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE LOWER(email) = ?", (clean_email,)
        ).fetchone()
        if existing is not None:
            raise ValueError("That email is already registered.")
        cursor = conn.execute(
            "INSERT INTO users (email, password_hash, name, ai_quota_used) "
            "VALUES (?, ?, ?, 0)",
            (clean_email, password_hash, clean_name),
        )
        user_id = cursor.lastrowid
        row = conn.execute(
            "SELECT id, email, name, ai_quota_used, created_at "
            "FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return dict(row)


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Find a user by email (case-insensitive)."""
    if not email:
        return None
    clean_email = email.strip().lower()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, email, password_hash, name, encrypted_ai_key, ai_quota_used, created_at "
            "FROM users WHERE LOWER(email) = ?",
            (clean_email,),
        ).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Find a user by primary key ID."""
    if not user_id:
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, email, password_hash, name, encrypted_ai_key, ai_quota_used, created_at "
            "FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None


def update_user_password(user_id: int, new_password_hash: str) -> bool:
    """Update password hash for a given user."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (new_password_hash, user_id),
        )
        return cursor.rowcount > 0


def update_user_ai_key(user_id: int, encrypted_key: Optional[str]) -> bool:
    """Store or clear encrypted BYOK API key for a user."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE users SET encrypted_ai_key = ? WHERE id = ?",
            (encrypted_key, user_id),
        )
        return cursor.rowcount > 0


def get_user_ai_key(user_id: int) -> str:
    """Return the decrypted user BYOK key, if one exists."""
    user = get_user_by_id(user_id)
    if not user or not user.get("encrypted_ai_key"):
        return ""
    from app.auth.security import decrypt_api_key

    return decrypt_api_key(user["encrypted_ai_key"])


def increment_user_ai_quota(user_id: int) -> int:
    """Atomically increment the user's free AI quota usage counter."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET ai_quota_used = ai_quota_used + 1 WHERE id = ?",
            (user_id,),
        )
        row = conn.execute(
            "SELECT ai_quota_used FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return row["ai_quota_used"] if row else 0


def get_or_create_default_user() -> Dict[str, Any]:
    """Ensure a default user (id=1) exists for local dev or tests."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, email, password_hash, name, encrypted_ai_key, ai_quota_used, created_at "
            "FROM users WHERE id = 1",
        ).fetchone()
        if row:
            return dict(row)
        # Create default user id=1
        conn.execute(
            "INSERT INTO users (id, email, password_hash, name, ai_quota_used) "
            "VALUES (1, 'owner@local', '', 'Owner', 0)"
        )
        row = conn.execute(
            "SELECT id, email, password_hash, name, encrypted_ai_key, ai_quota_used, created_at "
            "FROM users WHERE id = 1",
        ).fetchone()
        return dict(row)
