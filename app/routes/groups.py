"""Course Groups (Semesters) routes — Phase 11.

GET /groups — the management page: create a group, edit one, move courses
between groups, and delete a group with an explicit Option B choice
(D-022): "Ungroup courses" (preserves every course, group_id → NULL) or
"Delete group and all its courses" (atomic cascade per course).

Assignment is also reachable from every course's 3-dots menu
(POST /courses/{course_id}/group), so a course can be filed into a group
without leaving the sidebar or dashboard.
"""
from pathlib import Path

from fastapi import APIRouter, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.auth.dependencies import get_current_user
from app.roles import group_store
from app.roles.dashboard import list_dashboard_courses

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


def _render_groups(request: Request, user_id: int,
                   error: str | None = None):
    """Full /groups context: group blocks with their courses, the ungrouped
    course list, and every course (for the create-form multi-select)."""
    blocks = []
    for group in group_store.list_groups(user_id):
        blocks.append({
            "group": group,
            "courses": group_store.courses_in_group(group["id"], user_id),
        })
    return templates.TemplateResponse(
        request, "groups.html",
        {
            "groups": blocks,
            "ungrouped": group_store.list_ungrouped_courses(user_id),
            "all_courses": list_dashboard_courses(user_id),
            "error": error,
        },
    )


@router.get("/groups", response_class=HTMLResponse)
def groups_page(request: Request, user: dict = Depends(get_current_user)):
    return _render_groups(request, user["id"])


@router.post("/groups/create")
def groups_create(request: Request, name: str = Form(""),
                  description: str = Form(""),
                  timeframe_mode: str = Form("individual"),
                  timeframe_duration: str = Form(""),
                  course_ids: list[int] = Form([]),
                  user: dict = Depends(get_current_user)):
    """Create a group, optionally filing the checked courses into it."""
    try:
        group_id = group_store.create_group(
            user["id"], name, description, timeframe_mode,
            timeframe_duration)
    except ValueError as exc:
        return _render_groups(request, user["id"], error=str(exc))
    for course_id in course_ids:
        # Each assignment is individually safe (logs + validates); a
        # missing course simply stays ungrouped.
        group_store.set_course_group(course_id, group_id, user["id"])
    return RedirectResponse("/groups", status_code=303)


@router.post("/groups/{group_id}/update")
def groups_update(request: Request, group_id: int,
                  name: str = Form(""), description: str = Form(""),
                  timeframe_mode: str = Form("individual"),
                  timeframe_duration: str = Form(""),
                  status: str = Form("active"),
                  user: dict = Depends(get_current_user)):
    try:
        ok = group_store.update_group(
            user["id"], group_id, name=name, description=description,
            timeframe_mode=timeframe_mode,
            timeframe_duration=timeframe_duration, status=status)
    except ValueError as exc:
        return _render_groups(request, user["id"], error=str(exc))
    if not ok:
        return _render_groups(request, user["id"],
                              error="That group no longer exists.")
    return RedirectResponse("/groups", status_code=303)


@router.post("/groups/{group_id}/delete")
def groups_delete(request: Request, group_id: int,
                  action: str = Form(...),
                  user: dict = Depends(get_current_user)):
    """Option B (D-022): action = 'ungroup' (keep the courses) or
    'delete_courses' (cascade-delete them, then the group)."""
    try:
        affected = group_store.delete_group(group_id, action, user["id"])
    except ValueError as exc:
        return _render_groups(request, user["id"], error=str(exc))
    verb = "ungrouped" if action == "ungroup" else "deleted"
    return RedirectResponse(
        f"/groups?notice={affected} course"
        f"{'s' if affected != 1 else ''} {verb}",
        status_code=303,
    )


def _safe_redirect(path: str) -> str | None:
    """Only ever redirect to a same-site path (never an open redirect)."""
    if path and path.startswith("/") and not path.startswith("//"):
        return path
    return None


@router.post("/courses/{course_id}/group")
def course_group(course_id: int, group_id: str = Form(""),
                 next_path: str = Form("", alias="next"),
                 user: dict = Depends(get_current_user)):
    """Assign a course to a group (or ungroup it) from any course's
    3-dots menu or the course page. `next` bounces back to the page the
    form was on."""
    target = None
    if group_id.strip():
        try:
            target = int(group_id.strip())
        except ValueError:
            return RedirectResponse(
                _safe_redirect(next_path) or "/", status_code=303)
    ok = group_store.set_course_group(course_id, target, user["id"])
    if not ok:
        # Course or target group vanished — the safest landing is the
        # dashboard, which renders cleanly either way.
        return RedirectResponse("/", status_code=303)
    return RedirectResponse(_safe_redirect(next_path) or "/", status_code=303)