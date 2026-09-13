"""Settings page — Phase 7 (completion pass).

- API key display: masked, read-only. It reads the SAME variable the provider
  actually uses (AI_API_KEY via app/ai/config.load_config), so the page never
  claims a key exists when the app can't call, or shows "(not set)" when it can.
- Roommate cadence: editable, validated (>= 1 day), persisted to .env so it
  survives a restart — not just the current process.
- Per-Course default: "start new courses paused". Persisted to .env; read by
  course_store.confirm_curriculum when a Course is confirmed (replaces the old
  "coming in a future phase" placeholder).
"""
import os
from pathlib import Path

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.ai.config import load_config
from app.db import get_db_path
from app.roles import roommate
from app.roles.roommate_store import last_backup_info

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


def get_current_settings() -> dict:
    """Read current settings from the environment (after loading .env once)."""
    cfg = load_config()
    cadence = int(os.environ.get(
        "ROOMMATE_CADENCE_DAYS", str(roommate.DEFAULT_CADENCE_DAYS)))
    return {
        "api_key_masked": mask_api_key(cfg.api_key),
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
    settings = get_current_settings()
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "settings": settings,
            "error": None,
            "default_cadence": roommate.DEFAULT_CADENCE_DAYS,
            "db_path": str(get_db_path()),
            "backup": last_backup_info(),
        },
    )


@router.post("/settings")
def update_settings(
    request: Request,
    cadence_days: int = Form(...),
    new_courses_start_paused: str = Form(""),
):
    """Update cadence + per-course default; persist both to .env."""
    if cadence_days < 1:
        return templates.TemplateResponse(
            request,
            "settings.html",
            {
                "settings": get_current_settings(),
                "error": "Cadence must be at least 1 day.",
                "default_cadence": roommate.DEFAULT_CADENCE_DAYS,
                "db_path": str(get_db_path()),
                "backup": last_backup_info(),
            },
            status_code=400,
        )
    paused = "true" if new_courses_start_paused == "on" else "false"
    os.environ["ROOMMATE_CADENCE_DAYS"] = str(cadence_days)
    os.environ["NEW_COURSES_START_PAUSED"] = paused
    write_env_value("ROOMMATE_CADENCE_DAYS", str(cadence_days))
    write_env_value("NEW_COURSES_START_PAUSED", paused)
    return RedirectResponse("/settings", status_code=303)
