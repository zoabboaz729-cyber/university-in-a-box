"""Phase 7 DoD — backup & restore proof (docs/03 Phase 7 step 2).

The documented backup routine is "copy data/university.db somewhere safe";
'restore' is copying it back. Because the app is a single SQLite file this
test proves the routine end to end: back up the live DB file, then mount the
copy in a brand-new directory (a fresh machine / after a wipe) and read the
same rows back. init_db on the restored copy must be a no-op for schema and
migrations.
"""
import shutil
import sqlite3

from app.db import get_db_path, init_db
from tests.test_dashboard import seed_course


def test_backup_then_restore_keeps_rows(tmp_path, monkeypatch):
    live_dir = tmp_path / "live"
    monkeypatch.setenv("DATA_DIR", str(live_dir))
    init_db()
    course_id, topic_ids = seed_course(
        "Backup Me", topics=[("B1", "not_started"), ("B2", "done")])

    # Backup = the documented one-command file copy.
    backup_file = tmp_path / "university.db.backup-20260913-000000"
    shutil.copy2(get_db_path(), backup_file)

    # Restore = place the copy where data/ would be (fresh dir, new machine).
    fresh_dir = tmp_path / "restored"
    fresh_dir.mkdir(exist_ok=True)
    shutil.copy2(backup_file, fresh_dir / "university.db")
    monkeypatch.setenv("DATA_DIR", str(fresh_dir))
    init_db()  # schema + migrations must be no-ops on an already-restored DB

    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT title, status FROM courses WHERE id = ?",
            (course_id,)).fetchone()
        topics = conn.execute(
            "SELECT title FROM topics WHERE course_id = ? ORDER BY order_index",
            (course_id,)).fetchall()
    assert row["title"] == "Backup Me"
    assert row["status"] == "active"
    assert [t["title"] for t in topics] == ["B1", "B2"]
    assert len(topic_ids) == 2