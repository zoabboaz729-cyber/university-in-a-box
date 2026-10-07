"""Settings page — Phase 7 + Phase 13 + Phase 15.

- API key display: masked, read-only. It reads the SAME variable the provider
  actually uses (AI_API_KEY via app/ai/config.load_config), so the page never
  claims a key exists when the app can't call, or shows "(not set)" when it can.
- BYOK access: users can save their own OpenAI/OpenRouter key, encrypted at
  rest before it is written to the DB.
- Roommate cadence: editable, validated (>= 1 day), persisted to .env so it
  survives a restart — not just the current process.
- Per-Course default: "start new courses paused". Persisted to .env; read by
  course_store.confirm_curriculum when a Course is confirmed.
- Web push subscriptions: opt-in from the Settings page with VAPID public key
  support, subject to the user being signed in.
"""
import os
from pathlib import Path

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.ai.config import load_config
from app.auth.security import decrypt_api_key, encrypt_api_key
from app.auth.store import get_user_by_id, update_user_ai_key
from app.db import get_db_path
from app.roles import roommate
from app.roles.roommate_store import last_backup_info
from app.scheduler.notifications import (
    get_vapid_public_key,
    has_push_subscription,
    save_push_subscription,
    delete_push_subscription,
)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()

# Repo-root .env. Module-level so tests can point it at a temp file and a
# test run never rewrites the real .env.
ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


def mask_api_key(key: str | None) -> str:
    """Mask all but the last 4 chars of an API key for display."""
    if not key:
        return "(not set)"
    if len(key) <= 4:
        return "●●●●"
    return "●" * (len(key) - 4) + key[-4:]


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def get_current_settings(user: dict | None = None) -> dict:
    """Read current settings from the environment and the active user."""
    cfg = load_config()
    cadence = int(os.environ.get(
        "ROOMMATE_CADENCE_DAYS", str(roommate.DEFAULT_CADENCE_DAYS)))
    byok_key = ""
    if user and user.get("id"):
        stored = get_user_by_id(user["id"]) or {}
        byok_key = decrypt_api_key(stored.get("encrypted_ai_key"))
    return {
        "api_key_masked": mask_api_key(cfg.api_key),
        "byok_masked": mask_api_key(byok_key),
        "has_byok": bool(byok_key),
        "cadence_days": cadence,
        "new_courses_start_paused": _env_bool("NEW_COURSES_START_PAUSED"),
    }


def write_env_value(key: str, value: str) -> None:
    """Set key=value in the repo-root .env, preserving every other line.

    Only ever called for the two user-editable settings (cadence, per-course
    default) — never for secrets or the AI_* values. If .env is missing it is
    created, so the setting survives a restart on a fresh checkout as well as
    in the running process.
    """
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    else:
        lines = []
    out = []
    found = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            out.append(line)
            continue
        name, _, _ = stripped.partition("=")
        if name.strip() != key:
            out.append(line)
            continue
        out.append(key + "=" + value)
        found = True
    if not found:
        out.append(key + "=" + value)
    ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")


@router.get("/settings", response_class=HTMLResponse)
def show_settings(request: Request):
    user = getattr(request.state, "user", None)
    settings = get_current_settings(user)
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "settings": settings,
            "error": None,
            "default_cadence": roommate.DEFAULT_CADENCE_DAYS,
            "db_path": str(get_db_path()),
            "backup": last_backup_info(),
            "user": user,
            "vapid_public_key": get_vapid_public_key(),
            "push_enabled": bool(user and has_push_subscription(user["id"])),
        },
    )


@router.post("/settings")
def update_settings(
    request: Request,
    cadence_days: int = Form(...),
    new_courses_start_paused: str = Form(""),
    personal_ai_key: str = Form(""),
    clear_personal_ai_key: str = Form(""),
    push_enabled: str = Form(""),
    push_endpoint: str = Form(""),
    push_p256dh: str = Form(""),
    push_auth: str = Form(""),
    clear_push_subscription: str = Form(""),
):
    """Update cadence + per-course default; persist both to .env."""
    user = getattr(request.state, "user", None)
    if cadence_days < 1:
        return templates.TemplateResponse(
            request,
            "settings.html",
            {
                "settings": get_current_settings(user),
                "error": "Cadence must be at least 1 day.",
                "default_cadence": roommate.DEFAULT_CADENCE_DAYS,
                "db_path": str(get_db_path()),
                "backup": last_backup_info(),
                "user": user,
                "vapid_public_key": get_vapid_public_key(),
                "push_enabled": bool(user and has_push_subscription(user["id"])),
            },
            status_code=400,
        )
    if user and user.get("id"):
        if clear_personal_ai_key == "on":
            update_user_ai_key(user["id"], None)
        elif personal_ai_key.strip():
            update_user_ai_key(user["id"], encrypt_api_key(personal_ai_key.strip()))
        if clear_push_subscription == "on" or push_enabled != "on":
            delete_push_subscription(user["id"])
        elif push_endpoint.strip() and push_p256dh.strip() and push_auth.strip():
            save_push_subscription(
                user["id"],
                push_endpoint.strip(),
                push_p256dh.strip(),
                push_auth.strip(),
                True,
            )
    paused = "true" if new_courses_start_paused == "on" else "false"
    os.environ["ROOMMATE_CADENCE_DAYS"] = str(cadence_days)
    os.environ["NEW_COURSES_START_PAUSED"] = paused
    write_env_value("ROOMMATE_CADENCE_DAYS", str(cadence_days))
    write_env_value("NEW_COURSES_START_PAUSED", paused)
    return RedirectResponse("/settings", status_code=303)
