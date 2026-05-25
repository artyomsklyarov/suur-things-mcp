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


def test_update_needs_token_when_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("THINGS_AUTH_TOKEN", raising=False)
    # Also disable the token-file fallback so "unset" really means no token.
    monkeypatch.setenv("SUUR_THINGS_TOKEN_FILE", str(tmp_path / "no-token"))
    assert client.post("/api/update", json={"id": "x", "title": "y"}).json()["ok"] is False


def test_auth_token_reads_file_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("THINGS_AUTH_TOKEN", raising=False)
    tok = tmp_path / "token"
    tok.write_text("  abc123\n")
    monkeypatch.setenv("SUUR_THINGS_TOKEN_FILE", str(tok))
    import importlib

    from suur_things_mcp import config as cfg
    importlib.reload(cfg)
    assert cfg.auth_token() == "abc123"  # trimmed
    monkeypatch.setenv("THINGS_AUTH_TOKEN", "envwins")
    assert cfg.auth_token() == "envwins"  # env takes precedence


def test_placement_and_priority_overlays_validated(tmp_path, monkeypatch):
    monkeypatch.setenv("SUUR_THINGS_CONFIG", str(tmp_path / "board.json"))
    import importlib

    from suur_things_mcp import config as cfg
    importlib.reload(cfg)
    saved = cfg.save({
        "boards": [{"id": "b", "name": "B", "columns": ["A"], "placements": {"t1": "A", "t2": "Z"}}],
        "priority": {"x": "do", "y": "nope"},
    })
    # placement to a non-existent column is dropped; invalid quadrant is dropped.
    assert saved["boards"][0]["placements"] == {"t1": "A"}
    assert saved["priority"] == {"x": "do"}


@pytest.mark.skipif(not _things_available(), reason="Things database not available")
def test_board_endpoint_shape():
    b = client.get("/api/board?id=default").json()
    assert b["ok"] is True and "columns" in b and "auth" in b


def test_link_table_multi_repo_and_normalization(tmp_path, monkeypatch):
    monkeypatch.setenv("SUUR_THINGS_CONFIG", str(tmp_path / "board.json"))
    import importlib

    from suur_things_mcp import config as cfg
    importlib.reload(cfg)
    repo_a = tmp_path / "app"; repo_a.mkdir()
    repo_b = tmp_path / "web"; repo_b.mkdir()
    cfg.set_link("PROOF", "project", str(repo_a), "owner/proof-ios", "iOS app")
    cfg.set_link("PROOF", "project", str(repo_b), "https://github.com/owner/proof-web.git", "Website")
    repos = cfg.links()["PROOF"]["repos"]
    assert len(repos) == 2
    assert {r["github"] for r in repos} == {"owner/proof-ios", "owner/proof-web"}  # URL normalized
    # bad github is dropped to None
    cfg.set_link("X", "project", str(tmp_path / "x"), "not a repo slug")
    (tmp_path / "x").mkdir()
    assert cfg.links()["X"]["repos"][0]["github"] is None


def test_link_for_path_longest_match_and_stale(tmp_path, monkeypatch):
    monkeypatch.setenv("SUUR_THINGS_CONFIG", str(tmp_path / "board.json"))
    import importlib

    from suur_things_mcp import config as cfg
    importlib.reload(cfg)
    parent = tmp_path / "dev"; parent.mkdir()
    child = parent / "ilty"; child.mkdir()
    cfg.set_link("DEV", "area", str(parent))
    cfg.set_link("ILTY", "project", str(child))
    # a path inside the child resolves to the deeper (longest) repo
    assert cfg.link_for_path(str(child / "src"))["item_id"] == "ILTY"
    assert cfg.link_for_path(str(parent / "other"))["item_id"] == "DEV"
    # stale repo (deleted) is skipped
    cfg.set_link("GONE", "project", str(tmp_path / "missing"))
    assert cfg.link_for_path(str(tmp_path / "missing")) is None


def test_open_endpoint_validates_without_shelling(monkeypatch, tmp_path):
    # Guard against bad input; none of these reach subprocess.
    monkeypatch.setenv("SUUR_THINGS_CONFIG", str(tmp_path / "board.json"))
    import importlib

    from suur_things_mcp import config as cfg
    importlib.reload(cfg)
    assert client.post("/api/open", json={"item_id": "nope", "target": "editor"}).json()["ok"] is False
    cfg.set_link("P", "project", str(tmp_path), "owner/repo")
    assert client.post("/api/open", json={"item_id": "P", "repo_index": 9, "target": "github"}).json()["ok"] is False
    assert client.post("/api/open", json={"item_id": "P", "repo_index": 0, "target": "evil"}).json()["ok"] is False


def test_origin_guard_blocks_cross_site():
    cross = client.post("/api/config", headers={"sec-fetch-site": "cross-site"}, json={"boards": []})
    assert cross.status_code == 403
    bad = client.post("/api/config", headers={"origin": "http://evil.example"}, json={"boards": []})
    assert bad.status_code == 403


@pytest.mark.skipif(not _things_available(), reason="Things database not available")
def test_board_cards_are_projects_and_areas():
    from suur_things_mcp import reads as r
    sb = r.sidebar()
    area = next(a for a in sb["areas"] if a["projects"])
    cards = r.board_cards({
        "include_areas": [area["uuid"]],
        "include_projects": [area["projects"][0]["uuid"]],
        "columns": [],
    })
    assert any(c["kind"] == "area" for c in cards)
    assert any(c["kind"] == "project" for c in cards)
    assert all({"progress", "open", "total", "title"} <= set(c) for c in cards)


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
