"""Phase 7 completion — data/app.log error logging (docs/06-MONITORING §A).

The app was claiming error visibility it didn't have (no log file anywhere).
These tests prove: setup_logging() writes to data/app.log next to the DB and
is idempotent, and a real Roommate LLM failure during a dashboard load leaves
a trace there instead of dying silently.
"""
import time

from app.db import init_db
from app.monitor import get_logger, setup_logging
from tests.test_dashboard import make_client, seed_course


def test_setup_logging_writes_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    init_db()
    setup_logging()
    get_logger().warning("boom %s", "detail")
    log_path = tmp_path / "app.log"
    assert log_path.exists()
    assert "boom detail" in log_path.read_text(encoding="utf-8")

    # A second setup_logging() must not stack a duplicate file handler.
    setup_logging()
    get_logger().warning("again")
    assert log_path.read_text(encoding="utf-8").count("again") == 1


def test_dashboard_llm_failure_is_logged(tmp_path, monkeypatch):
    # conftest's autouse NoNetworkProvider makes the dashboard Roommate
    # due-check fail for every active course: the background thread must
    # write a trace to data/app.log rather than vanish silently.
    client = make_client(tmp_path, monkeypatch)
    seed_course("Fail Course", topics=[("F1", "not_started")])
    setup_logging()
    client.get("/")
    time.sleep(0.5)  # the thread raises immediately; this just lets it finish
    log_path = tmp_path / "app.log"
    assert log_path.exists()
    assert "Roommate" in log_path.read_text(encoding="utf-8")