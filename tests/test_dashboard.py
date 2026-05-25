"""Dashboard tests.

The `/` route is static and runs anywhere. The data routes need a readable
Things database, so they skip gracefully when Things isn't present (CI / Linux).
"""

import pytest
from starlette.testclient import TestClient

from suur_things_mcp import reads
from suur_things_mcp.dashboard import _pick_port, create_app

client = TestClient(create_app())


def _things_available() -> bool:
    try:
        reads.board()
        return True
    except Exception:
        return False


def test_index_route_is_static():
    r = client.get("/")
    assert r.status_code == 200
    assert 'id="sidebar"' in r.text and "/api/sidebar" in r.text


def test_pick_port_returns_free_port():
    port = _pick_port()
    assert isinstance(port, int) and 1 <= port <= 65535


def test_state_endpoint_never_500s():
    # Even with no Things DB, the endpoint returns a JSON envelope, not a 500.
    r = client.get("/api/state")
    assert r.status_code == 200
    body = r.json()
    assert "ok" in body and "board" in body


@pytest.mark.skipif(not _things_available(), reason="Things database not available")
def test_state_shape_with_things():
    body = client.get("/api/state").json()
    assert body["ok"] is True
    for col in ("inbox", "today", "upcoming", "anytime", "someday"):
        assert col in body["board"]


@pytest.mark.skipif(not _things_available(), reason="Things database not available")
def test_sidebar_endpoint_shape():
    sb = client.get("/api/sidebar").json()
    assert sb["ok"] is True
    assert {"builtins", "areas", "arealess"} <= set(sb["sidebar"])
    assert any(b["id"] == "today" for b in sb["sidebar"]["builtins"])


@pytest.mark.skipif(not _things_available(), reason="Things database not available")
def test_items_endpoint_shape():
    it = client.get("/api/items?id=today").json()
    assert it["ok"] is True and it["kind"] == "builtin" and isinstance(it["items"], list)


def test_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("SUUR_THINGS_CONFIG", str(tmp_path / "board.json"))
    import importlib

    from suur_things_mcp import config as cfg
    importlib.reload(cfg)
    saved = cfg.save({"boards": [
        {"id": "b1", "name": "Dev", "columns": ["A", " B ", ""], "include_areas": ["x"], "include_projects": []}
    ]})
    board = saved["boards"][0]
    assert board["columns"] == ["A", "B"]  # trimmed, empties dropped
    assert board["include_areas"] == ["x"] and board["id"] == "b1"
    assert cfg.get_board("b1")["name"] == "Dev"


def test_config_migrates_legacy_flat(tmp_path, monkeypatch):
    monkeypatch.setenv("SUUR_THINGS_CONFIG", str(tmp_path / "board.json"))
    import importlib

    from suur_things_mcp import config as cfg
    importlib.reload(cfg)
    cfg.save({"columns": ["X"], "include_areas": ["a"]})  # legacy flat shape
    loaded = cfg.load()
    assert loaded["boards"][0]["id"] == "default"
    assert loaded["boards"][0]["columns"] == ["X"]


def test_config_defaults_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("SUUR_THINGS_CONFIG", str(tmp_path / "nope.json"))
    import importlib

    from suur_things_mcp import config as cfg
    importlib.reload(cfg)
    boards = cfg.load()["boards"]
    assert boards[0]["id"] == "default" and boards[0]["columns"] == cfg.DEFAULT_COLUMNS


def test_move_and_update_need_token_when_unset(monkeypatch):
    monkeypatch.delenv("THINGS_AUTH_TOKEN", raising=False)
    assert client.post("/api/update", json={"id": "x", "title": "y"}).json()["ok"] is False
    assert client.post("/api/move", json={"id": "x", "column": "Done"}).json()["ok"] is False


def test_tags_after_move_preserves_non_status_tags(monkeypatch):
    # Pure function: dropping status tags, keeping the rest, adding the target.
    from suur_things_mcp import reads as r
    monkeypatch.setattr(r, "get", lambda uuid, **k: {"tags": ["SUUR", "Backlog"]})
    cols = {"Backlog", "In Progress", "Done"}
    assert r.tags_after_move("x", "Done", cols) == ["SUUR", "Done"]
    assert r.tags_after_move("x", None, cols) == ["SUUR"]


@pytest.mark.skipif(not _things_available(), reason="Things database not available")
def test_board_endpoint_shape():
    b = client.get("/api/board?id=default").json()
    assert b["ok"] is True and "columns" in b and "auth" in b


def test_board_endpoint_unknown_id():
    b = client.get("/api/board?id=does-not-exist").json()
    assert b["ok"] is False


@pytest.mark.skipif(not _things_available(), reason="Things database not available")
def test_overview_shape_with_things():
    ov = reads.overview(recent_completed=5)
    assert set(ov) == {
        "counts",
        "today",
        "overdue",
        "projects_without_next_action",
        "recent_completed",
    }
    assert "today" in ov["counts"]
