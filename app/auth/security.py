"""Password hashing and session token security utilities.

Uses Argon2id (via argon2-cffi) for password hashing and itsdangerous
URLSafeTimedSerializer for signed session tokens.
"""
import base64
import hashlib
import os

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

SESSION_COOKIE_NAME = "university_session"
SESSION_MAX_AGE_SECONDS = 30 * 86400  # 30 days
DEV_SECRET_FALLBACK = "dev-insecure-secret-key-change-in-production-12345"

_hasher = PasswordHasher()


def get_secret_key() -> str:
    """Retrieve APP_SECRET_KEY from environment or return dev fallback."""
    return os.environ.get("APP_SECRET_KEY", DEV_SECRET_FALLBACK)


def _aes_key() -> bytes:
    """Derive a 32-byte AES key from the application secret."""
    digest = hashlib.sha256(get_secret_key().encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)[:32]


def encrypt_api_key(plain_api_key: str) -> str:
    """Encrypt a user BYOK key with AES-GCM and return a transport-safe string."""
    if not plain_api_key:
        return ""
    nonce = os.urandom(12)
    ciphertext = AESGCM(_aes_key()).encrypt(nonce, plain_api_key.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_api_key(payload: str | None) -> str:
    """Decrypt a stored BYOK key, returning the original plaintext or blank on failure."""
    if not payload:
        return ""
    try:
        raw = base64.b64decode(payload.encode("ascii"), validate=True)
        if len(raw) < 12 + 16:
            return ""
        nonce = raw[:12]
        ciphertext = raw[12:]
        return AESGCM(_aes_key()).decrypt(nonce, ciphertext, None).decode("utf-8")
    except Exception:
        return ""


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    if not plain_password:
        raise ValueError("Password cannot be empty")
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an Argon2id hash."""
    if not plain_password or not hashed_password:
        return False
    try:
        return _hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_session_token(user_id: int) -> str:
    """Generate a signed URL-safe session token containing the user ID."""
    serializer = URLSafeTimedSerializer(get_secret_key(), salt="user-session")
    return serializer.dumps({"uid": user_id})


def verify_session_token(token: str, max_age_seconds: int = SESSION_MAX_AGE_SECONDS) -> int | None:
    """Verify a signed session token. Returns user_id if valid, else None."""
    if not token:
        return None
    serializer = URLSafeTimedSerializer(get_secret_key(), salt="user-session")
    try:
        data = serializer.loads(token, max_age=max_age_seconds)
        if isinstance(data, dict) and "uid" in data:
            return int(data["uid"])
        return None
    except (BadSignature, SignatureExpired, Exception):
        return None


# Session cookie is HttpOnly + SameSite=Lax always; Secure only when the app
# is served over HTTPS (production), so plain-http local dev keeps working.
COOKIE_SAMESITE = "lax"


def cookie_secure() -> bool:
    """True when the session cookie must carry the Secure flag.

    Off by default (local http://127.0.0.1 works); set APP_COOKIE_SECURE=true
    in production behind HTTPS.
    """
    return os.environ.get("APP_COOKIE_SECURE", "").strip().lower() in (
        "1", "true", "yes", "on")


def safe_next(next_url: str | None, default: str = "/") -> str:
    """Allow only same-site relative redirect targets (no open redirects)."""
    if next_url and next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return default
