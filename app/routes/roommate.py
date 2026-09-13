"""Roommate routes — Phase 6: Insights journal + reactions.

GET /roommate lists every Roommate prompt newest first, each with an
optional free-text reaction field. The journal NEVER calls the LLM — it
is a passive history; generation happens on dashboard load (the
due-check in routes/dashboard.py).
POST /roommate/prompts/{id}/reaction saves that reaction.
"""
from pathlib import Path

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.roles.roommate_store import (
    MAX_REACTION_CHARS,
    list_all_prompts,
    save_reaction,
)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


@router.get("/roommate", response_class=HTMLResponse)
def journal(request: Request):
    return templates.TemplateResponse(
        request, "roommate.html", {"prompts": list_all_prompts()}
    )


@router.post("/roommate/prompts/{prompt_id}/reaction")
def reaction(request: Request, prompt_id: int, reaction: str = Form(...)):
    if len(reaction) > MAX_REACTION_CHARS:
        return templates.TemplateResponse(
            request, "roommate.html",
            {"prompts": list_all_prompts(),
             "error": f"Keep the reaction under {MAX_REACTION_CHARS} "
                      "characters."},
            status_code=400,
        )
    try:
        ok = save_reaction(prompt_id, reaction)
    except ValueError as exc:
        return templates.TemplateResponse(
            request, "roommate.html",
            {"prompts": list_all_prompts(), "error": str(exc)},
            status_code=400,
        )
    if not ok:
        return templates.TemplateResponse(
            request, "error.html",
            {"message": "That prompt no longer exists. It may have been "
                        "deleted."},
            status_code=404,
        )
    return RedirectResponse("/roommate", status_code=303)