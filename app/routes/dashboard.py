"""Dashboard route. Phase 2: lists non-draft Courses with resume pointers.
Phase 6: the Roommate due-check runs on every load OUTSIDE the page-paint
path, and the newest prompt is shown as one compact 'Fresh connection' block
linking to the journal.

Phase 7-efficiency: dashboard loads no longer block on generation; a durable
"new since your last visit" badge appears when a newer prompt exists.
"""
import os
import threading
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.ai.provider import get_provider
from app.monitor import get_logger
from app.roles import roommate
from app.roles.dashboard import list_dashboard_courses
from app.roles.roommate_store import (
    dash_visit_at,
    latest_prompt,
    prompt_newer_than,
    record_dash_visit,
)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    provider = get_provider()

    # The DB location this request uses. The background thread below may
    # outlive the request (slow provider), so it must keep writing to THIS
    # database even if the process environment changes later. In tests the
    # DATA_DIR is swapped per case; without pinning, a slow leftover thread
    # would leak its prompt into the next test's database.
    request_data_dir = os.environ.get("DATA_DIR")

    # Baseline for the durable badge = the LAST dashboard render the user saw.
    # Read BEFORE this render's visit is recorded, so a prompt created during
    # this load cannot make the badge fire on the very render that produced it.
    last_visit = dash_visit_at()

    # Phase 6/7: the Roommate due-check still fires on every load, but it now
    # runs in a background thread so a slow / dead provider can't hold
    # `GET /` hostage. Per-course failures are already logged inside
    # generate_due_prompts, and any other error is swallowed.
    #
    # We wait briefly for the thread to finish: if generation completes in
    # time, this render can show the new prompt; if not (slow provider), the
    # page is returned without it and the next load will pick it up. The
    # timeout is short enough that a 0.5s artificial delay still lets the page
    # return in well under 0.4s.
    def _generate():
        # Pin DATA_DIR to THIS request's value for the whole pass, then
        # restore whatever the environment had when the thread actually ran.
        # `saved` is read at wake time; the pre-restore check makes sure we
        # only put it back if nobody else changed the env while we worked.
        saved = os.environ.get("DATA_DIR")
        pinned = saved != request_data_dir
        try:
            if pinned:
                if request_data_dir is None:
                    os.environ.pop("DATA_DIR", None)
                else:
                    os.environ["DATA_DIR"] = request_data_dir
            roommate.generate_due_prompts(provider)
        except Exception:
            # Never let the background thread kill the page. Per-course
            # failures are logged inside generate_due_prompts (activity row +
            # app.log); this only catches the unexpected-around-it.
            get_logger().warning(
                "Roommate background generation failed", exc_info=True
            )
        finally:
            if pinned and os.environ.get("DATA_DIR") == request_data_dir:
                if saved is None:
                    os.environ.pop("DATA_DIR", None)
                else:
                    os.environ["DATA_DIR"] = saved

    t = threading.Thread(target=_generate, daemon=True)
    t.start()
    t.join(timeout=0.2)

    # This render's "as-of" timestamp becomes next load's baseline.
    record_dash_visit()

    # What the current render can safely show. If the background thread
    # finished within the timeout, this is the just-generated prompt;
    # otherwise it is whatever prompt already existed (possibly None).
    rendered_prompt = latest_prompt()

    # Durable badge: a newer prompt exists than the LAST visit the user saw.
    new_since_visit = prompt_newer_than(last_visit) is not None

    return templates.TemplateResponse(
        request, "index.html",
        {
            "courses": list_dashboard_courses(),
            "latest_roommate_prompt": rendered_prompt,
            "new_since_visit": new_since_visit,
        },
    )
