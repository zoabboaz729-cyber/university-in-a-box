"""FastAPI entry point. Boots the app, creates the DB, serves routes.

NOTE: the FastAPI instance is named `api` (not `app`) on purpose: the repo
root's parent also contains an installed `app` package shadow, and
`from app.main import app` can bind the shadowing MODULE instead of this
instance (see D-008). `api` is unambiguous everywhere.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db import init_db
from app.monitor import get_logger, setup_logging
from app.roles.dashboard import list_dashboard_courses
from app.routes.advisor import router as advisor_router
from app.routes.advisor import templates as advisor_templates
from app.routes.courses import router as courses_router
from app.routes.courses import templates as courses_templates
from app.routes.dashboard import router as dashboard_router
from app.routes.dashboard import templates as dashboard_templates
from app.routes.editor import router as editor_router
from app.routes.editor import templates as editor_templates
from app.routes.librarian import router as librarian_router
from app.routes.librarian import templates as librarian_templates
from app.routes.roommate import router as roommate_router
from app.routes.roommate import templates as roommate_templates
from app.routes.settings import router as settings_router
from app.routes.settings import templates as settings_templates
from app.routes.tutor import router as tutor_router
from app.routes.tutor import templates as tutor_templates

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(api: FastAPI):
    # Create data/university.db with all tables on first boot (no-op after).
    init_db()
    # data/app.log receives failed-LLM / unhandled errors (docs/06-MONITORING).
    setup_logging()
    yield


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


# Serve self-hosted CSS, JS, and fonts from /static.
api.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

api.include_router(dashboard_router)
api.include_router(advisor_router)
api.include_router(courses_router)
api.include_router(editor_router)
api.include_router(librarian_router)
api.include_router(roommate_router)
api.include_router(settings_router)
api.include_router(tutor_router)

# Backwards-compatible alias for `uvicorn app.main:app` invocations.
app = api

# Inject sidebar_courses as a Jinja2 env global into every router's
# Templates instance so base.html can render the persistent sidebar course
# list without each route handler passing it explicitly.
# list_dashboard_courses is called at render time → always reads live DB.
for _templates in (
    advisor_templates, courses_templates, dashboard_templates,
    editor_templates, librarian_templates, roommate_templates,
    settings_templates, tutor_templates,
):
    _templates.env.globals["sidebar_courses"] = list_dashboard_courses

# Registers review handlers onto the advisor router (import for side
# effects; split out of advisor.py only to keep files short per constraints).
# NOTE: must be a `from`-import. `import app.routes.advisor_review` would
# rebind the module-global name `app` to the `app` package MODULE (Python's
# `import a.b.c` binds `a`), clobbering the alias above — uvicorn
# `app.main:app` would then load a module, not this ASGI app (bug fixed 2026-09-13).
from app.routes import advisor_review  # noqa: E402,F401
