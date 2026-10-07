"""FastAPI entry point. Boots the app, creates the DB, serves routes.

NOTE: the FastAPI instance is named `api` (not `app`) on purpose: the repo
root's parent also contains an installed `app` package shadow, and
`from app.main import app` can bind the shadowing MODULE instead of this
instance (see D-008). `api` is unambiguous everywhere.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from app.auth.dependencies import get_current_user, get_current_user_optional
from app.db import init_db
from app.monitor import get_logger, setup_logging
from app.roles import group_store
from app.routes.advisor import router as advisor_router
from app.routes.advisor import templates as advisor_templates
from app.routes.auth import router as auth_router
from app.routes.courses import router as courses_router
from app.routes.courses import templates as courses_templates
from app.routes.dashboard import router as dashboard_router
from app.routes.dashboard import templates as dashboard_templates
from app.routes.editor import router as editor_router
from app.routes.editor import templates as editor_templates
from app.routes.groups import router as groups_router
from app.routes.groups import templates as groups_templates
from app.routes.librarian import router as librarian_router
from app.routes.librarian import templates as librarian_templates
from app.routes.roommate import router as roommate_router
from app.routes.roommate import templates as roommate_templates
from app.routes.settings import router as settings_router
from app.routes.settings import templates as settings_templates
from app.routes.tutor import router as tutor_router
from app.routes.tutor import templates as tutor_templates
from app.scheduler import start_scheduler, stop_scheduler

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(api: FastAPI):
    # Create data/university.db with all tables on first boot (no-op after).
    init_db()
    # data/app.log receives failed-LLM / unhandled errors (docs/06-MONITORING).
    setup_logging()
    await start_scheduler()
    try:
        yield
    finally:
        await stop_scheduler()


api = FastAPI(title="University in a Box", lifespan=lifespan)


@api.middleware("http")
async def catch_and_log(request, call_next):
    """Write any unhandled exception to data/app.log, then re-raise."""
    try:
        return await call_next(request)
    except Exception:
        get_logger().exception(
            "Unhandled error on %s %s", request.method, request.url.path
        )
        raise


@api.middleware("http")
async def attach_current_user(request, call_next):
    """Stash the signed-in user on request.state for templates (base.html).

    Always sets the attribute (None when logged out) so templates can read
    request.state.user unconditionally. /static is skipped — assets never
    need the user and this keeps them from touching the DB.

    Phase 12: when a test overrides the get_current_user dependency, honor
    the same override here so templates (sidebar, group dropdowns) see the
    very user the route handlers see.
    """
    if request.url.path.startswith("/static"):
        request.state.user = None
    else:
        override = api.dependency_overrides.get(get_current_user)
        request.state.user = (override() if override
                              else get_current_user_optional(request))
    return await call_next(request)


# Serve self-hosted CSS, JS, and fonts from /static.
api.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Public: authentication (register / login / logout). Never gated.
api.include_router(auth_router)

# Protected: every learning router requires a signed-in user. The router-level
# dependency bounces unauthenticated requests to /login; handlers additionally
# receive the user (Depends(get_current_user)) to scope their data queries.
_protected = [Depends(get_current_user)]
api.include_router(dashboard_router, dependencies=_protected)
api.include_router(advisor_router, dependencies=_protected)
api.include_router(courses_router, dependencies=_protected)
api.include_router(editor_router, dependencies=_protected)
api.include_router(groups_router, dependencies=_protected)
api.include_router(librarian_router, dependencies=_protected)
api.include_router(roommate_router, dependencies=_protected)
api.include_router(settings_router, dependencies=_protected)
api.include_router(tutor_router, dependencies=_protected)

# Backwards-compatible alias for `uvicorn app.main:app` invocations.
app = api

# Inject sidebar/course-group helpers as Jinja2 env globals into every
# router's Templates instance so base.html can render the persistent sidebar
# course list without each route handler passing it explicitly.
# sidebar_groups is called at render time → always reads live DB. It is
# the Phase 11 replacement for sidebar_courses: a structured list of
# group blocks ({"group": {...}|None, "courses": [...]}) so the sidebar
# can render collapsible Semester folders with zero route churn.
# all_groups feeds every "move to group" dropdown (the 3-dots menu modal,
# the course page select, the /groups page).
# Phase 12: both are per-user — they read the signed-in user that
# attach_current_user stashed on request.state (templates always receive
# `request`), and render empty when nobody is signed in.
from jinja2 import pass_context  # noqa: E402


def _template_user(ctx):
    """The signed-in user for a template render, or None (logged out)."""
    request = ctx.get("request")
    if request is None:
        return None
    return getattr(request.state, "user", None)


@pass_context
def _sidebar_groups(ctx):
    user = _template_user(ctx)
    return group_store.sidebar_groups(user["id"]) if user else []


@pass_context
def _all_groups(ctx):
    user = _template_user(ctx)
    return group_store.list_groups(user["id"]) if user else []


for _templates in (
    advisor_templates, courses_templates, dashboard_templates,
    editor_templates, groups_templates, librarian_templates,
    roommate_templates, settings_templates, tutor_templates,
):
    _templates.env.globals["sidebar_groups"] = _sidebar_groups
    _templates.env.globals["all_groups"] = _all_groups

# Registers review handlers onto the advisor router (import for side
# effects; split out of advisor.py only to keep files short per constraints).
# NOTE: must be a `from`-import. `import app.routes.advisor_review` would
# rebind the module-global name `app` to the `app` package MODULE (Python's
# `import a.b.c` binds `a`), clobbering the alias above — uvicorn
# `app.main:app` would then load a module, not this ASGI app (bug fixed 2026-09-13).
from app.routes import advisor_review  # noqa: E402,F401
