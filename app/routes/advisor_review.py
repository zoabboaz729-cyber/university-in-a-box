"""Advisor interview: draft review + confirm (appended to the advisor router)."""
from fastapi import Form
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.requests import Request

from app.ai.provider import ProviderError, get_provider
from app.roles import advisor
from app.roles.activity import log
from app.roles.course_store import confirm_curriculum
from app.roles.interview_store import get_interview
from app.routes.advisor import not_found, render_step, router, templates


@router.post("/{interview_id}/regenerate")
def regenerate_draft(request: Request, interview_id: int):
    """Regenerate button: re-run the single draft call from saved answers."""
    interview = get_interview(interview_id)
    if interview is None:
        return not_found(request, "Interview not found.")
    if advisor.next_step(set(interview["answers"])) is not None:
        return RedirectResponse(f"/advisor/{interview_id}", status_code=303)
    return review_draft(request, interview_id)


@router.get("/{interview_id}/review", response_class=HTMLResponse)
def review_draft(request: Request, interview_id: int):
    interview = get_interview(interview_id)
    if interview is None:
        return not_found(request, "Interview not found.")
    if advisor.next_step(set(interview["answers"])) is not None:
        return RedirectResponse(f"/advisor/{interview_id}", status_code=303)
    try:
        draft = advisor.build_draft(
            interview["topic"], interview["answers"], get_provider()
        )
    except ProviderError as exc:
        # No draft yet — back to the last step with a clear, retryable error.
        interview = get_interview(interview_id)
        return render_step(
            request, interview_id, advisor.STEPS[-1], interview,
            error="Could not generate the draft: " + str(exc),
        )
    except Exception as exc:
        interview = get_interview(interview_id)
        return render_step(
            request, interview_id, advisor.STEPS[-1], interview,
            error="The draft came back in a bad shape (" + str(exc) + "). "
                  "Please go back and check your answers, then try again.",
        )
    return templates.TemplateResponse(
        request, "advisor_review.html",
        {"interview_id": interview_id, "topic": interview["topic"], "draft": draft},
    )


def _collect_topics(form: dict, count: int) -> list[dict]:
    """Pull per-topic edited fields out of the confirm form.

    form keys: title-N / milestone-N / timebox-N (N from 0). Rows with a
    blank title or milestone are dropped (they'd corrupt the course).
    """
    topics = []
    for index in range(count):
        title = (form.get(f"title-{index}", "") or "").strip()
        milestone = (form.get(f"milestone-{index}", "") or "").strip()
        if not title or not milestone:
            continue
        topics.append(
            {
                "title": title,
                "milestone_description": milestone,
                "time_box": (form.get(f"timebox-{index}", "") or "").strip(),
            }
        )
    return topics


@router.post("/{interview_id}/confirm")
async def confirm_course(
    request: Request, interview_id: int,
    course_title: str = Form(...),
    title_0: str = Form(""), milestone_0: str = Form(""), timebox_0: str = Form(""),
):
    """Save the edited draft as a real Course (Phase 1c), then show it.

    Reads the editable fields. A fixed first-topic parameter set is declared
    for FastAPI's form handling; remaining topics arrive via request.form()
    (awaited — Request.form() is async in current Starlette).
    """
    interview = get_interview(interview_id)
    if interview is None:
        return not_found(request, "Interview not found.")
    if advisor.next_step(set(interview["answers"])) is not None:
        # Interview isn't finished — can't confirm a curriculum yet.
        return RedirectResponse(f"/advisor/{interview_id}", status_code=303)

    form = dict(await request.form())
    # Gather every topic's fields via form (title-N / milestone-N / timebox-N).
    count = max(1, len([k for k in form if k.startswith("title-")]))
    topics = _collect_topics(form, count)
    if not topics or not course_title.strip():
        # No LLM call needed here: the typed values are already in this POST,
        # so rebuild the review page from them and show a clear inline error
        # instead of bouncing the user back to a step question. Every row is
        # preserved (even blank ones), so the user never loses what they typed
        # and always has an editable box in front of them.
        raw_topics = [
            advisor.DraftTopic(
                title=(form.get(f"title-{index}", "") or "").strip(),
                milestone_description=(
                    form.get(f"milestone-{index}", "") or ""
                ).strip(),
                time_box=(form.get(f"timebox-{index}", "") or "").strip(),
            )
            for index in range(count)
        ]
        draft = advisor.CurriculumDraft(
            course_title=course_title.strip(), topics=raw_topics
        )
        return templates.TemplateResponse(
            request, "advisor_review.html",
            {
                "interview_id": interview_id,
                "topic": interview["topic"],
                "draft": draft,
                "error": "The course needs a title and at least one topic with a "
                         "milestone. Edit the boxes above and try again.",
            },
        )

    confirm_curriculum(
        interview_id, course_title.strip(), topics, interview["answers"]
    )
    log(interview_id, "course", interview_id, "confirmed")
    return RedirectResponse(f"/courses/{interview_id}", status_code=303)
