"""MCP tool-layer behavior: write verification and read-tool token budgets.

Uses the fixture Things DB from conftest.py; the URL Scheme itself is stubbed
(`execute`) so nothing is ever dispatched to a real Things app.
"""

import pytest

from suur_things_mcp import server


@pytest.fixture
def fired(monkeypatch):
    """Stub urlscheme execution; records (command, params) per call."""
    calls = []

    def fake_execute(command, params, auth_token=None, requires_auth=None):
        calls.append((command, dict(params)))
        return f"things:///{command}?stubbed"

    monkeypatch.setattr(server, "execute", fake_execute)
    return calls


# --- write verification -----------------------------------------------------

def test_update_rejects_missing_uuid(things_db, fired):
    res = server.complete_todo("no-such-uuid")
    assert res["ok"] is False
    assert "no item with UUID" in res["error"]
    assert fired == []  # nothing was dispatched to Things


def test_update_reports_applied(things_db, fired, monkeypatch):
    # Simulate Things applying the write: the item's modified stamp changes
    # after the URL fires.
    stamps = iter(["t0", "t0", "t1"])  # exists-check, before-snapshot, first poll
    monkeypatch.setattr(server, "_modified_stamp", lambda uuid: next(stamps, "t1"))
    monkeypatch.setattr(server, "_item_missing", lambda uuid: False)
    res = server.complete_todo("todo-today")
    assert res["ok"] is True and res["applied"] is True
    assert fired[0][0] == "update" and fired[0][1]["completed"] is True


def test_update_warns_when_unverified(things_db, fired, monkeypatch):
    monkeypatch.setattr(server, "_modified_stamp", lambda uuid: "t0")  # never changes
    monkeypatch.setattr(server.time, "sleep", lambda s: None)
    res = server.schedule_todo("todo-today", "tomorrow")
    assert res["ok"] is True and res["applied"] is False
    assert "verify with get_item" in res["warning_unverified"]


def test_unknown_tags_warned_on_update(things_db, fired, monkeypatch):
    monkeypatch.setattr(server.time, "sleep", lambda s: None)
    res = server.update_todo(id="todo-today", tags=["urgent", "nonexistent-tag"])
    assert res["ok"] is True
    assert "nonexistent-tag" in res["tag_warning"]
    assert "urgent" not in res["tag_warning"]  # existing tag: no complaint


def test_unknown_tags_warned_on_add(things_db, fired):
    res = server.add_todo(title="New task", tags=["nope"])
    assert res["ok"] is True
    assert "nope" in res["tag_warning"]
    res2 = server.add_todo(title="New task", tags=["home"])
    assert "tag_warning" not in res2


# --- read-tool token budgets -------------------------------------------------

def test_reads_compact_by_default(things_db):
    items = server.get_today()
    assert items and all("notes" not in i and "has_notes" in i for i in items)
    full = server.get_today(compact=False)
    assert any("notes" in i for i in full)


def test_search_caps_results(things_db):
    assert len(server.search_todos("a", limit=1)) <= 1
    items = server.search_todos("report")
    assert items and "has_notes" in items[0]


def test_list_todos_limit_and_shape(things_db):
    items = server.list_todos(area_uuid="area-work", limit=1)
    assert len(items) == 1 and "has_notes" in items[0]
