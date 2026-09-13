"""Advisor interview routes — Phase 1b (part 1: start + step display).

GET /advisor/new → topic form. POST → creates draft course, redirects to step 1.
GET /advisor/{id} → exactly one question (or resume at the next unanswered step).
GET /advisor/{id}/edit/{step} → back-button: re-ask an answered step for editing.
"""
from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from pathlib import Path

from app.roles import advisor
from app.roles.activity import log
from app.roles.interview_store import get_interview, save_answer, start_interview

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(prefix="/advisor")


@router.get("/new", response_class=HTMLResponse)
def new_interview(request: Request):
    return templates.TemplateResponse(request, "advisor_new.html")


@router.post("/new")
def create_interview(topic: str = Form(...)):
    topic = topic.strip()
    if not topic:
        return RedirectResponse("/advisor/new", status_code=303)
    interview_id = start_interview(topic)
    log(interview_id, "interview", interview_id, "started")
    return RedirectResponse(f"/advisor/{interview_id}", status_code=303)


def render_step(request: Request, interview_id: int, step: str, interview: dict,
                error: str = ""):
    """Render exactly one question. Shared by show/edit/submit/review-error."""
    steps = advisor.STEPS
    return templates.TemplateResponse(
        request,
        "advisor_step.html",
        {
            "interview_id": interview_id,
            "topic": interview["topic"],
            "step": step,
            "step_number": steps.index(step) + 1,
            "step_count": len(steps),
            "question": advisor.question_for(step),
            "saved_answer": interview["answers"].get(step, ""),
            "prev_step": prev_answered(interview["answers"], step),
            "error": error,
        },
    )


def prev_answered(answers: dict, step: str) -> str | None:
    """Latest answered step before `step`, for the Back button (None if none)."""
    prev = None
    for s in advisor.STEPS:
        if s == step:
            return prev
        if s in answers:
            prev = s
    return None


def not_found(request: Request, message: str):
    return templates.TemplateResponse(
        request, "error.html", {"message": message}, status_code=404
    )


@router.get("/{interview_id}", response_class=HTMLResponse)
def show_step(request: Request, interview_id: int):
    interview = get_interview(interview_id)
    if interview is None:
        return not_found(request, "Interview not found. It may have been deleted.")
    step = advisor.next_step(set(interview["answers"]))
    if step is None:
        return RedirectResponse(f"/advisor/{interview_id}/review", status_code=303)
    return render_step(request, interview_id, step, interview)


@router.get("/{interview_id}/edit/{step}", response_class=HTMLResponse)
def edit_step(request: Request, interview_id: int, step: str):
    interview = get_interview(interview_id)
    if interview is None or step not in advisor.STEPS:
        return not_found(request, "Interview or step not found.")
    if step not in interview["answers"]:
        # Nothing to edit — send them to where they actually are.
        return RedirectResponse(f"/advisor/{interview_id}", status_code=303)
    return render_step(request, interview_id, step, interview)


@router.post("/{interview_id}")
def submit_answer(
    request: Request, interview_id: int,
    step: str = Form(...), answer: str = Form(...),
):
    interview = get_interview(interview_id)
    if interview is None or step not in advisor.STEPS:
        return not_found(request, "Interview or step not found.")
    if not answer.strip():
        # Empty answer: re-show the same question with an inline error.
        return render_step(
            request, interview_id, step, interview,
            error="Please write an answer before continuing.",
        )
    save_answer(interview_id, step, advisor.question_for(step), answer)
    log(interview_id, "interview", interview_id, "answered:" + step)
    interview = get_interview(interview_id)
    if advisor.next_step(set(interview["answers"])) is None:
        return RedirectResponse(f"/advisor/{interview_id}/review", status_code=303)
    return RedirectResponse(f"/advisor/{interview_id}", status_code=303)
