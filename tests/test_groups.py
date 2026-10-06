"""Phase 11 tests: course groups / semesters, timeframe modes, group
deletion (Option B: ungroup vs delete courses), and intra-group Roommate
synthesis (P5)."""
import json
import sqlite3

import pytest

from app.db import get_db_path, init_db
from app.roles import group_store, roommate
from app.roles.course_manage import delete_course
from app.roles.roommate_store import (
    list_all_prompts,
    peer_course,
    save_prompt,
)
from tests.test_dashboard import make_client, seed_course


class FakeProvider:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def generate(self, system_prompt, user_message):
        self.calls += 1
        return self.replies[min(self.calls - 1, len(self.replies) - 1)]


GOOD = json.dumps({
    "field": "architecture",
    "prompt": "Consider how an architect would separate the load-bearing "
              "structure of your topic from its decorative parts.",
})


def _init(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    init_db()


def _seed_grouped(tmp_path, monkeypatch, group_name="Semester 1"):
    """A group with two ACTIVE courses (A = older id, B = newer id)."""
    _init(tmp_path, monkeypatch)
    a_id, _ = seed_course("Course A", topics=[("TA", "not_started")])
    b_id, _ = seed_course("Course B", topics=[("TB", "not_started")])
    group_id = group_store.create_group(1, group_name)
    group_store.set_course_group(a_id, group_id, 1)
    group_store.set_course_group(b_id, group_id, 1)
    return group_id, a_id, b_id


def _prompt_row(prompt_id):
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT * FROM roommate_prompts WHERE id = ?", (prompt_id,)
        ).fetchone()


# --- schema & migration ------------------------------------------------


def test_schema_has_group_tables_and_columns(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    init_db()  # run twice: migrations must stay idempotent
    with sqlite3.connect(get_db_path()) as conn:
        groups = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='course_groups'").fetchone()
        assert groups is not None
        course_cols = {row[1] for row in conn.execute(
            "PRAGMA table_info(courses)")}
        assert "group_id" in course_cols
        prompt_cols = {row[1] for row in conn.execute(
            "PRAGMA table_info(roommate_prompts)")}
        assert "secondary_course_id" in prompt_cols
        assert "connection_type" in prompt_cols


# --- group CRUD --------------------------------------------------------


def test_create_group_defaults_and_progress(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    group_id = group_store.create_group(1, "Semester 1")
    group = group_store.get_group(group_id, 1)
    assert group["name"] == "Semester 1"
    assert group["timeframe_mode"] == "individual"  # D-022 Option A default
    assert group["description"] is None
    # No courses yet → zero aggregates.
    assert group["course_count"] == 0
    assert group["total_topics"] == 0

    cid, _ = seed_course("OS", topics=[("T1", "done"), ("T2", "not_started")])
    group_store.set_course_group(cid, group_id, 1)
    group = group_store.get_group(group_id, 1)
    assert group["course_count"] == 1
    assert group["total_topics"] == 2
    assert group["done_topics"] == 1
    assert group["active_course_count"] == 1


def test_create_group_validation(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        group_store.create_group(1, "   ")
    with pytest.raises(ValueError):
        group_store.create_group(1, "G", timeframe_mode="weekly")


def test_update_group(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    group_id = group_store.create_group(1, "Semester 1")
    ok = group_store.update_group(
        1, group_id, name="Semester 1: Systems",
        timeframe_mode="uniform", timeframe_duration="12 weeks",
        status="completed")
    assert ok is True
    group = group_store.get_group(group_id, 1)
    assert group["name"] == "Semester 1: Systems"
    assert group["timeframe_mode"] == "uniform"
    assert group["timeframe_duration"] == "12 weeks"
    assert group["status"] == "completed"
    assert group_store.update_group(1, 99999, name="X") is False
    with pytest.raises(ValueError):
        group_store.update_group(1, group_id, timeframe_mode="bogus")


def test_assign_and_ungroup_course(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    cid, _ = seed_course("Course", topics=[("T", "not_started")])
    group_id = group_store.create_group(1, "G")
    assert group_store.set_course_group(cid, group_id, 1) is True
    assert [c["id"] for c in group_store.courses_in_group(group_id, 1)] == [cid]
    assert group_store.list_ungrouped_courses(1) == []
    # Ungroup
    assert group_store.set_course_group(cid, None, 1) is True
    assert group_store.courses_in_group(group_id, 1) == []
    assert [c["id"] for c in group_store.list_ungrouped_courses(1)] == [cid]
    # Validation
    assert group_store.set_course_group(cid, 99999, 1) is False
    assert group_store.set_course_group(99999, group_id, 1) is False


# --- group deletion (Option B, D-022) ----------------------------------


def test_delete_group_ungroup_preserves_courses(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    group_id, a_id, b_id = _seed_grouped(tmp_path, monkeypatch)
    affected = group_store.delete_group(group_id, "ungroup", 1)
    assert affected == 2
    assert group_store.get_group(group_id, 1) is None
    with sqlite3.connect(get_db_path()) as conn:
        rows = conn.execute(
            "SELECT COUNT(*) FROM courses WHERE group_id = ?", (group_id,)
        ).fetchone()
        kept = conn.execute(
            "SELECT COUNT(*) FROM courses WHERE id IN (?, ?)",
            (a_id, b_id)).fetchone()
    assert rows[0] == 0
    assert kept[0] == 2  # both courses survive, fully intact


def test_delete_group_with_courses_cascades(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    group_id, a_id, _ = _seed_grouped(tmp_path, monkeypatch)
    save_prompt(a_id, "architecture", "Prompt for A", 1)
    affected = group_store.delete_group(group_id, "delete_courses", 1)
    assert affected == 2
    assert group_store.get_group(group_id, 1) is None
    with sqlite3.connect(get_db_path()) as conn:
        courses = conn.execute(
            "SELECT COUNT(*) FROM courses WHERE id IN (?, ?)",
            (a_id, 999)).fetchone()
        prompts = conn.execute(
            "SELECT COUNT(*) FROM roommate_prompts").fetchone()
    assert courses[0] == 0
    assert prompts[0] == 0


def test_delete_group_validation(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    group_id = group_store.create_group(1, "G")
    with pytest.raises(ValueError):
        group_store.delete_group(group_id, "explode", 1)
    with pytest.raises(ValueError):
        group_store.delete_group(99999, "ungroup", 1)


# --- sidebar structure --------------------------------------------------


def test_sidebar_groups_structure(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    g1 = group_store.create_group(1, "Semester 1")
    g2 = group_store.create_group(1, "Semester 2")
    c1, _ = seed_course("OS", topics=[("T", "not_started")])
    c2, _ = seed_course("DB", topics=[("T", "not_started")])
    c3, _ = seed_course("Italian", topics=[("T", "not_started")])
    group_store.set_course_group(c1, g1, 1)
    group_store.set_course_group(c3, g2, 1)
    blocks = group_store.sidebar_groups(1)
    # Two non-empty groups first, then the ungrouped block.
    assert blocks[0]["group"]["id"] == g1
    assert [c["id"] for c in blocks[0]["courses"]] == [c1]
    assert blocks[1]["group"]["id"] == g2
    assert [c["id"] for c in blocks[1]["courses"]] == [c3]
    assert blocks[2]["group"] is None
    assert [c["id"] for c in blocks[2]["courses"]] == [c2]
    # An empty group is not listed in the sidebar at all.
    group_store.create_group(1, "Empty")
    assert len(group_store.sidebar_groups(1)) == 3


# --- intra-group Roommate synthesis (P5) --------------------------------


def test_peer_course_finds_active_groupmate(tmp_path, monkeypatch):
    _, a_id, b_id = _seed_grouped(tmp_path, monkeypatch)
    peer = peer_course(a_id, 1)
    assert peer is not None
    assert peer["id"] == b_id
    assert peer["current_topic_title"] == "TB"
    # A third, PAUSED course in the group is never a peer.
    c3, _ = seed_course("Course C", status="paused",
                        topics=[("TC", "not_started")])
    g_id = group_store.list_groups(1)[0]["id"]
    group_store.set_course_group(c3, g_id, 1)
    assert peer_course(c3, 1) is None
    # An ungrouped course has no peer.
    solo, _ = seed_course("Solo", topics=[("TS", "not_started")])
    assert peer_course(solo, 1) is None


def test_build_intra_group_prompt_parses_and_retries():
    conn = roommate.build_intra_group_prompt(
        "Operating Systems", "Understand kernels", "Page cache",
        "Databases", "DB internals", "B-trees", [],
        FakeProvider([GOOD]))
    assert conn.field == "architecture"
    provider = FakeProvider(["nope", GOOD])
    conn = roommate.build_intra_group_prompt(
        "A", "", "a", "B", "", "b", [], provider)
    assert conn.field == "architecture"
    assert provider.calls == 2


def test_generate_due_prompts_bridges_group_pair(tmp_path, monkeypatch):
    _, a_id, b_id = _seed_grouped(tmp_path, monkeypatch)
    created = roommate.generate_due_prompts(FakeProvider([GOOD]), 1)
    # Both courses were due → one bridge from each side.
    assert len(created) == 2
    rows = list_all_prompts(1)
    by_course = {r["course_id"]: r for r in rows}
    assert by_course[a_id]["connection_type"] == "intra_group"
    assert by_course[a_id]["secondary_course_id"] == b_id
    assert by_course[b_id]["connection_type"] == "intra_group"
    assert by_course[b_id]["secondary_course_id"] == a_id
    # Journal rows carry BOTH course titles for the ↔ display.
    assert rows[0]["secondary_course_title"] is not None
    # Second pass: nothing due (prompts are fresh) → no extra prompts.
    assert roommate.generate_due_prompts(FakeProvider([GOOD]), 1) == []


def test_generate_external_without_group_peer(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    cid, _ = seed_course("Solo", topics=[("T", "not_started")])
    roommate.generate_due_prompts(FakeProvider([GOOD]), 1)
    rows = list_all_prompts(1)
    assert len(rows) == 1
    assert rows[0]["course_id"] == cid
    assert rows[0]["connection_type"] == "external"
    assert rows[0]["secondary_course_id"] is None


def test_save_prompt_validates_secondary(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    a_id, _ = seed_course("A", topics=[("T", "not_started")])
    b_id, _ = seed_course("B", topics=[("T", "not_started")])
    with pytest.raises(ValueError):
        save_prompt(a_id, "f", "p", 1, secondary_course_id=a_id,
                    connection_type="intra_group")
    with pytest.raises(ValueError):
        save_prompt(a_id, "f", "p", 1, secondary_course_id=99999,
                    connection_type="intra_group")
    with pytest.raises(ValueError):
        save_prompt(a_id, "f", "p", 1, secondary_course_id=b_id,
                    connection_type="weird")
    # A valid intra-group prompt saves cleanly.
    pid = save_prompt(a_id, "cache × b-tree", "Bridge.", 1,
                      secondary_course_id=b_id, connection_type="intra_group")
    row = _prompt_row(pid)
    assert row["secondary_course_id"] == b_id
    assert row["connection_type"] == "intra_group"


def test_delete_course_nulls_secondary_references(tmp_path, monkeypatch):
    _, a_id, b_id = _seed_grouped(tmp_path, monkeypatch)
    pid = save_prompt(a_id, "cache × b-tree", "Bridge.", 1,
                      secondary_course_id=b_id, connection_type="intra_group")
    delete_course(b_id, 1)
    row = _prompt_row(pid)
    assert row["secondary_course_id"] is None  # no dangling bridge


# --- routes & UI --------------------------------------------------------


def test_groups_page_renders_management_ui(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    _seed_grouped(tmp_path, monkeypatch, group_name="Semester 1")
    seed_course("Italian", topics=[("I", "not_started")])
    resp = client.get("/groups")
    assert resp.status_code == 200
    assert "Create a group" in resp.text
    assert "Semester 1" in resp.text
    assert "individual" in resp.text
    assert "Ungrouped courses" in resp.text
    assert "Delete this group" in resp.text
    assert "Ungroup its" in resp.text
    assert "Delete group and all its courses permanently" in resp.text


def test_group_routes_create_assign_delete(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    c_id, _ = seed_course("Course", topics=[("T", "not_started")])

    # Create via route, filing the course in immediately.
    resp = client.post("/groups/create",
                       data={"name": "Track 1", "description": "d",
                             "timeframe_mode": "individual",
                             "course_ids": [str(c_id)]},
                       follow_redirects=False)
    assert resp.status_code == 303
    groups = group_store.list_groups(1)
    assert len(groups) == 1
    g_id = groups[0]["id"]
    assert [c["id"] for c in group_store.courses_in_group(g_id, 1)] == [c_id]

    # Move the course out via the assign route (3-dots menu path).
    resp = client.post(f"/courses/{c_id}/group",
                       data={"group_id": "", "next": "/"},
                       follow_redirects=False)
    assert resp.status_code == 303
    assert group_store.courses_in_group(g_id, 1) == []

    # Delete the group with the Option-B 'ungroup' action.
    resp = client.post(f"/groups/{g_id}/delete",
                       data={"action": "ungroup"}, follow_redirects=False)
    assert resp.status_code == 303
    assert group_store.get_group(g_id, 1) is None
    assert client.get(f"/courses/{c_id}").status_code == 200


def test_dashboard_group_filter(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    g_id, a_id, b_id = _seed_grouped(tmp_path, monkeypatch)
    u_id, _ = seed_course("Ungrouped Course", topics=[("U", "not_started")])

    # Default view: group card + both grouped courses + ungrouped row.
    all_resp = client.get("/")
    assert all_resp.status_code == 200
    assert "Semester 1" in all_resp.text
    assert "group-card" in all_resp.text
    assert 'href="/?group=none"' in all_resp.text  # filter pill

    # Filter to the group: only its courses appear in the MAIN list (the
    # sidebar always lists every course, the filter narrows the list only).
    g_resp = client.get(f"/?group={g_id}")
    # Slice only the <main> content: document-level modals after it (the
    # mobile nav dialog) legitimately list every course, like the sidebar.
    main_g = g_resp.text.split("<main>", 1)[1].split("</main>", 1)[0]
    assert f'href="/courses/{a_id}"' in main_g
    assert f'href="/courses/{b_id}"' in main_g
    assert f'href="/courses/{u_id}"' not in main_g

    # Filter to ungrouped: only the lone course appears in the main list.
    n_resp = client.get("/?group=none")
    main_n = n_resp.text.split("<main>", 1)[1].split("</main>", 1)[0]
    assert f'href="/courses/{u_id}"' in main_n
    assert f'href="/courses/{a_id}"' not in main_n


def test_course_page_group_select(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    g_id, a_id, _ = _seed_grouped(tmp_path, monkeypatch)
    resp = client.get(f"/courses/{a_id}")
    assert resp.status_code == 200
    assert "Group / Semester" in resp.text
    assert f'<option value="{g_id}" selected>' in resp.text
    assert "Semester 1" in resp.text
    assert f'/courses/{a_id}/group' in resp.text


def test_dashboard_renders_group_menus_and_modals(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    _, a_id, _ = _seed_grouped(tmp_path, monkeypatch)
    resp = client.get("/")
    assert f"sb-menu-{a_id}" in resp.text  # sidebar 3-dots survive groups
    assert f"dash-menu-{a_id}" in resp.text
    assert "Group / Semester" in resp.text  # new context-menu action
    assert "group-assign-modal" in resp.text
    assert "openGroupModal" in resp.text


def test_mobile_courses_nav_dialog_renders(tmp_path, monkeypatch):
    """Task 2: phones reach every course/group through the nav dialog."""
    client = make_client(tmp_path, monkeypatch)
    g_id, a_id, b_id = _seed_grouped(tmp_path, monkeypatch)
    resp = client.get("/")
    assert resp.status_code == 200
    assert 'id="mobile-courses-btn"' in resp.text
    assert "courses-nav-modal" in resp.text
    # Every grouped course is listed inside the dialog with its own
    # mnav-menu- id (unique next to sb-menu- and dash-menu-).
    assert f"mnav-menu-{a_id}" in resp.text
    assert f"mnav-menu-{b_id}" in resp.text
    assert "Semester 1" in resp.text
    assert f'href="/courses/{a_id}"' in resp.text


def test_group_creation_discoverable_on_dashboard(tmp_path, monkeypatch):
    """Task 3: a fresh, course-less, group-less account can reach the
    group-creation form in one click via visible affordances (nav item,
    dashboard button, empty-state link)."""
    client = make_client(tmp_path, monkeypatch)
    resp = client.get("/")
    assert resp.status_code == 200
    assert 'href="/groups"' in resp.text  # persistent sidebar nav item
    assert "New group" in resp.text       # dashboard secondary button
    assert resp.text.count('href="/groups"') >= 2


def test_journal_shows_intra_group_bridge(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    _, a_id, _ = _seed_grouped(tmp_path, monkeypatch)
    roommate.generate_due_prompts(FakeProvider([GOOD]), 1)
    resp = client.get("/roommate")
    assert resp.status_code == 200
    assert "Course A" in resp.text
    assert "↔ Course B" in resp.text
    # Intra-group bridges use the cross-course marker in the journal.
    assert "🪞" in resp.text