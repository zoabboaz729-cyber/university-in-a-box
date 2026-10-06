"""Authentication routes — Phase 12.

Public routes (never behind get_current_user): GET/POST /register, GET/POST
/login, POST /logout. A successful register/login sets the signed, HttpOnly
session cookie and redirects to a validated `next` target or the dashboard;
logout clears it.

Passwords are hashed with Argon2id (app/auth/security). These templates are
standalone (they do NOT extend base.html — its sidebar needs a signed-in
user), so a logged-out visitor sees a clean, minimal page.
"""
from pathlib import Path

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.auth.security import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    cookie_secure,
    create_session_token,
    hash_password,
    safe_next,
    verify_password,
)
from app.auth.store import create_user, get_user_by_email

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()

MIN_PASSWORD_CHARS = 8


def _set_session(response, user_id: int) -> None:
    """Attach the signed session cookie to a response."""
    response.set_cookie(
        SESSION_COOKIE_NAME,
        create_session_token(user_id),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=cookie_secure(),
        path="/",
    )


def _render(request, template, status_code=200, **context):
    return templates.TemplateResponse(
        request, template, context, status_code=status_code
    )


@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request, next: str = ""):
    return _render(
        request, "register.html",
        next_url=safe_next(next), error=None, name="", email="",
    )


@router.post("/register")
def register(
    request: Request,
    name: str = Form(""),
    email: str = Form(""),
    password: str = Form(""),
    confirm_password: str = Form(""),
    next: str = Form(""),
):
    target = safe_next(next)
    name = name.strip()
    email = email.strip()

    def fail(message: str):
        return _render(
            request, "register.html", status_code=400,
            next_url=target, error=message, name=name, email=email,
        )

    if not name:
        return fail("Please enter your name.")
    if "@" not in email or "." not in email.split("@")[-1]:
        return fail("Please enter a valid email address.")
    if len(password) < MIN_PASSWORD_CHARS:
        return fail(
            "Password must be at least " + str(MIN_PASSWORD_CHARS) + " characters."
        )
    if password != confirm_password:
        return fail("Passwords do not match.")

    try:
        user = create_user(email, hash_password(password), name)
    except ValueError as exc:
        return fail(str(exc))

    response = RedirectResponse(target, status_code=303)
    _set_session(response, user["id"])
    return response


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, next: str = ""):
    return _render(
        request, "login.html",
        next_url=safe_next(next), error=None, email="",
    )


@router.post("/login")
def login(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    next: str = Form(""),
):
    target = safe_next(next)
    user = get_user_by_email(email)
    if user is None or not verify_password(
        password, user.get("password_hash") or ""
    ):
        return _render(
            request, "login.html", status_code=401,
            next_url=target, error="Incorrect email or password.",
            email=email.strip(),
        )
    response = RedirectResponse(target, status_code=303)
    _set_session(response, user["id"])
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return response
