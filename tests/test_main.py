"""Phase 0 test: the app boots, / renders, and the DB has every table.

Runs against a temp DATA_DIR so it never touches the real data/university.db.
"""
import sqlite3

from fastapi.testclient import TestClient

from app.db import get_db_path
from app.models import TABLE_NAMES


def test_index_renders_and_db_has_all_tables(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    from app.main import api

    with TestClient(api) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "University in a Box" in response.text

    db_path = get_db_path()
    assert db_path.exists()

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    created = {row[0] for row in rows}
    for table in TABLE_NAMES:
        assert table in created, f"missing table: {table}"
