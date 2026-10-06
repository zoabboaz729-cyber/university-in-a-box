"""FastAPI authentication dependencies for route protection.

Only the learning routes import these. Every protected handler injects
`get_current_user`, which resolves the signed session cookie into the owning
user row or bounces the request to /login. An unauthenticated request must
never reach a data function.
"""
from typing import Optional, Dict, Any

from fastapi import Request, HTTPException

from app.auth.security import SESSION_COOKIE_NAME, verify_session_token
from app.auth.store import get_user_by_id

LOGIN_PATH = "/login"


def get_current_user_optional(request: Request) -> Optional[Dict[str, Any]]:
    """The signed-in user for this request, or None."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    user_id = verify_session_token(token)
    if not user_id:
        return None
    return get_user_by_id(user_id)


def get_current_user(request: Request) -> Dict[str, Any]:
    """Require a signed-in user; otherwise redirect to /login.

    Browser (HTML) requests get a 303 to /login?next=...; JSON callers get a
    401 so they can react without a full page bounce.
    """
    user = get_current_user_optional(request)
    if user:
        return user

    accept = request.headers.get("accept", "")
    if "application/json" in accept:
        raise HTTPException(status_code=401, detail="Authentication required")

    next_path = request.url.path
    if request.url.query:
        next_path += "?" + request.url.query
    raise HTTPException(
        status_code=303,
        headers={"Location": LOGIN_PATH + "?next=" + next_path},
    )
