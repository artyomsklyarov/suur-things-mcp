"""Dashboard tests.

The `/` route is static and runs anywhere. The data routes need a readable
Things database, so they skip gracefully when Things isn't present (CI / Linux).
"""

import json

import pytest
from starlette.testclient import TestClient

from suur_things_mcp import reads
from suur_things_mcp.dashboard import DEFAULT_PORT, _pick_port, create_app

# base_url sets the Host header to one TrustedHostMiddleware accepts (it strips the
# port, leaving 127.0.0.1). Default TestClient Host is "testserver", which the host
# allowlist would now (correctly) reject.
client = TestClient(create_app(), base_url=f"http://127.0.0.1:{DEFAULT_PORT}")


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


def test_quick_add_has_feedback_and_guards():
    """The quick-add submit path must keep its no-silent-failure guards: a
    re-entry lock, a button-disable/restore, and a try/catch around the request.
    These are embedded JS, so guard against accidental deletion at the source."""
    html = client.get("/").text
    assert "let CREATING=false" in html              # double-submit guard
    assert "if(CREATING) return" in html
    assert 'btn.disabled=true' in html and "btn.disabled=false" in html  # lock + restore
    assert "Adding image…" in html and "Adding…" in html                 # in-flight feedback


def test_attach_promise_always_settles():
    """uploadAttachmentTo() must never hang: a never-settling Promise would leave
    CREATING=true and the Add button stuck disabled. Both failure paths (file-read
    error, thrown fetch) must resolve(false), so the onerror handler and the
    try/catch in onload are load-bearing."""
    html = client.get("/").text
    assert "reader.onerror=" in html                 # failed read resolves instead of hanging
    # the fetch in reader.onload is wrapped so a thrown request also resolves(false)
    assert "}catch(e){ alert(\"Attach failed: " in html
    assert "const staged=PENDING_ATTACH.slice()" in html  # snapshot at submit time


def test_pick_port_returns_free_port():
    port = _pick_port()
    assert isinstance(port, int) and 1 <= port <= 65535


def test_dashboard_no_open_flag_suppresses_browser(monkeypatch):
    """`dashboard --no-open` runs as a quiet service (no browser). A login agent
    relies on this; without it, KeepAlive respawns pop a tab on every restart."""
    import sys

    import suur_things_mcp.dashboard as dash
    from suur_things_mcp import server

    captured = {}
    monkeypatch.setattr(dash, "serve_foreground", lambda **kw: captured.update(kw))
    monkeypatch.setattr(sys, "argv", ["suur-things-mcp", "dashboard", "--no-open"])
    server.main()
    assert captured == {"app_mode": False, "open_browser": False}


def test_dashboard_default_opens_browser(monkeypatch):
    import sys

    import suur_things_mcp.dashboard as dash
    from suur_things_mcp import server

    captured = {}
    monkeypatch.setattr(dash, "serve_foreground", lambda **kw: captured.update(kw))
    monkeypatch.setattr(sys, "argv", ["suur-things-mcp", "dashboard"])
    server.main()
    assert captured["open_browser"] is True and captured["app_mode"] is False


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


def test_repo_path_strips_surrounding_quotes(tmp_path, monkeypatch):
    monkeypatch.setenv("SUUR_THINGS_CONFIG", str(tmp_path / "board.json"))
    import importlib
    import os as _os

    from suur_things_mcp import config as cfg
    importlib.reload(cfg)
    d = tmp_path / "My Repo"; d.mkdir()
    cfg.set_link("P", "project", f"'{d}'")  # pasted shell-quoted path
    stored = cfg.links()["P"]["repos"][0]["repo"]
    assert stored == _os.path.normcase(_os.path.realpath(str(d)))  # quotes stripped, absolute


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


def test_merge_preserves_other_sections(tmp_path, monkeypatch):
    monkeypatch.setenv("SUUR_THINGS_CONFIG", str(tmp_path / "board.json"))
    import importlib

    from suur_things_mcp import config as cfg
    importlib.reload(cfg)
    repo = tmp_path / "r"; repo.mkdir()
    cfg.set_link("ILTY", "project", str(repo), "owner/ilty")
    # Saving ONLY boards must NOT wipe the link written separately (the old bug).
    cfg.merge({"boards": [{"id": "b", "name": "B", "columns": ["X"]}]})
    assert "ILTY" in cfg.load()["links"]
    assert cfg.load()["boards"][0]["name"] == "B"


def test_set_item_repos_isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SUUR_THINGS_CONFIG", str(tmp_path / "board.json"))
    import importlib

    from suur_things_mcp import config as cfg
    importlib.reload(cfg)
    a = tmp_path / "a"; a.mkdir()
    b = tmp_path / "b"; b.mkdir()
    cfg.set_link("A", "project", str(a))
    # Editing B's repos leaves A untouched; empty list removes the item.
    cfg.set_item_repos("B", "project", [{"repo": str(b), "label": "web"}])
    assert {"A", "B"} <= set(cfg.load()["links"])
    cfg.set_item_repos("B", "project", [])
    assert "B" not in cfg.load()["links"] and "A" in cfg.load()["links"]


def test_github_normalizes_ssh_and_url(tmp_path, monkeypatch):
    monkeypatch.setenv("SUUR_THINGS_CONFIG", str(tmp_path / "board.json"))
    import importlib

    from suur_things_mcp import config as cfg
    importlib.reload(cfg)
    assert cfg._normalize_github("git@github.com:owner/repo.git") == "owner/repo"
    assert cfg._normalize_github("https://github.com/owner/repo") == "owner/repo"
    assert cfg._normalize_github("owner/repo") == "owner/repo"
    assert cfg._normalize_github("https://gitlab.com/owner/repo") is None


def test_prefs_merge_isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SUUR_THINGS_CONFIG", str(tmp_path / "board.json"))
    import importlib

    from suur_things_mcp import config as cfg
    importlib.reload(cfg)
    cfg.set_link("X", "project", str(tmp_path))
    cfg.merge({"prefs": {"editor": "cursor", "terminal": "Ghostty", "bogus": "x"}})
    p = cfg.prefs()
    assert p == {"editor": "cursor", "terminal": "Ghostty"}  # unknown key dropped
    assert "X" in cfg.load()["links"]  # prefs save didn't wipe links


def test_organize_parser_handles_claude_envelope_and_fences():
    from suur_things_mcp import organize as org
    inner = '[{"uuid":"a","suggested_title":"Buy milk","append_notes":null,"tags":["Errand"],"reason":"clearer"}]'
    # claude --output-format json: array lives in a string field of an envelope
    env = json.dumps({"type": "result", "result": inner})
    out = org.parse_suggestions(env, "claude")
    assert out[0]["uuid"] == "a" and out[0]["suggested_title"] == "Buy milk"
    assert out[0]["tags"] == ["Errand"] and out[0]["append_notes"] is None
    # codex / plain: fenced + prose around it
    messy = 'Here you go:\n```json\n' + inner + '\n```\nDone.'
    out2 = org.parse_suggestions(messy, "codex")
    assert out2[0]["suggested_title"] == "Buy milk"


def test_organize_parser_drops_blank_titles_and_caps():
    from suur_things_mcp import organize as org
    arr = '[{"uuid":"x","suggested_title":"   ","tags":["a","b","c","d","e","f"]}]'
    out = org.parse_suggestions(arr, "codex")
    assert out[0]["suggested_title"] is None  # blank -> None
    assert len(out[0]["tags"]) == 5  # capped


def test_resolve_falls_back_to_login_path(monkeypatch):
    # The dashboard often launches with a minimal PATH (GUI/launchd), so a bare
    # `which` misses codex; _resolve must retry against the login-shell PATH.
    from suur_things_mcp import organize as org
    calls = []

    def fake_which(cmd, path=None):
        calls.append(path)
        return None if path is None else f"/fake/bin/{cmd}"

    monkeypatch.setattr(org.shutil, "which", fake_which)
    monkeypatch.setattr(org, "_login_path", lambda: "/fake/bin")
    assert org._resolve("codex") == "/fake/bin/codex"
    assert calls == [None, "/fake/bin"]  # bare attempt first, then login PATH


def test_pick_agent_uses_resolve(monkeypatch):
    from suur_things_mcp import organize as org
    monkeypatch.delenv("SUUR_THINGS_AGENT", raising=False)
    monkeypatch.setattr(org, "_resolve", lambda c: f"/x/{c}" if c == "codex" else None)
    assert org.pick_agent({}) == "codex"  # claude unresolved, codex found


@pytest.mark.skipif(not _things_available(), reason="Things database not available")
def test_builtin_lists_exclude_projects():
    # Bug #4: Anytime/Someday include projects; the list view must show to-dos only.
    for lid in ("anytime", "someday", "today"):
        items = reads.list_items(lid)["items"]
        assert all(i.get("type") == "to-do" for i in items), f"{lid} leaked a project"


def test_organize_needs_token(monkeypatch, tmp_path):
    monkeypatch.delenv("THINGS_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("SUUR_THINGS_TOKEN_FILE", str(tmp_path / "no-token"))
    r = client.post("/api/organize", json={"folder_id": "today"}).json()
    assert r["ok"] is False and "TOKEN" in r["error"].upper()


def test_organize_unknown_job():
    assert client.get("/api/organize?job_id=nope").json()["status"] == "unknown"


def test_update_supports_additive_writes(monkeypatch):
    # The organize apply path relies on append_notes / add_tags reaching the URL params.
    monkeypatch.delenv("THINGS_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("SUUR_THINGS_TOKEN_FILE", "/nonexistent")
    # No token -> ok False, but the endpoint must accept the fields without erroring.
    r = client.post("/api/update", json={"id": "x", "append_notes": "n", "add_tags": ["t"]}).json()
    assert r["ok"] is False  # token gate, not a crash


# 1x1 transparent PNG
_PNG_1x1 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
            "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


def test_attachments_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("SUUR_THINGS_CONFIG", str(tmp_path / "board.json"))
    import importlib
    from suur_things_mcp import config as cfg
    importlib.reload(cfg)
    cfg.set_link("X", "project", str(tmp_path))  # an unrelated section
    meta = cfg.save_attachment("T", b"\x89PNG\r\n fake", "image/png", "shot.png", caption="hi")
    # bytes on disk, metadata recorded, other sections untouched
    assert cfg.attachment_path("T", meta).exists()
    assert cfg.attachment_meta("T", meta["id"])["mime"] == "image/png"
    assert "X" in cfg.load()["links"]
    # a non-image mime is refused
    with pytest.raises(ValueError):
        cfg.save_attachment("T", b"x", "application/pdf", "x.pdf")
    # remove deletes both
    assert cfg.remove_attachment("T", meta["id"]) is True
    assert not cfg.attachment_path("T", meta).exists()
    assert cfg.attachments().get("T") is None


def test_note_ref_line_marks_image_and_links_file():
    from suur_things_mcp import config as cfg
    url = cfg.note_ref_url("/Users/me/.config/x y/img.png")
    assert url == "file:///Users/me/.config/x%20y/img.png"  # path is URL-quoted
    line = cfg.note_ref_line("chart.png", "/tmp/chart.png")
    assert "Image attached" in line and "chart.png" in line  # clear indicator for Things
    assert line.endswith(cfg.note_ref_url("/tmp/chart.png"))  # ends with the tappable file:// URL


def test_attach_serve_detach_endpoints(tmp_path, monkeypatch):
    monkeypatch.setenv("SUUR_THINGS_CONFIG", str(tmp_path / "board.json"))
    monkeypatch.delenv("THINGS_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("SUUR_THINGS_TOKEN_FILE", str(tmp_path / "no-token"))
    r = client.post("/api/attach", json={"uuid": "TASK1", "name": "shot.png",
                                         "mime": "image/png", "data": _PNG_1x1}).json()
    assert r["ok"] is True and r["note_updated"] is False  # no token -> overlay only
    aid = r["attachment"]["id"]
    g = client.get(f"/api/attachment?uuid=TASK1&id={aid}")
    assert g.status_code == 200 and g.headers["content-type"].startswith("image/png")
    assert g.content[:8] == b"\x89PNG\r\n\x1a\n"
    # only known ids serve; unknown id and a traversal-shaped request both 404
    assert client.get("/api/attachment?uuid=TASK1&id=nope").status_code == 404
    assert client.get("/api/attachment?uuid=../../etc&id=passwd").status_code == 404
    assert client.post("/api/detach", json={"uuid": "TASK1", "id": aid}).json()["ok"] is True
    assert client.get(f"/api/attachment?uuid=TASK1&id={aid}").status_code == 404


def test_attach_rejects_non_image(tmp_path, monkeypatch):
    monkeypatch.setenv("SUUR_THINGS_CONFIG", str(tmp_path / "board.json"))
    r = client.post("/api/attach", json={"uuid": "T", "mime": "application/pdf",
                                         "data": _PNG_1x1}).json()
    assert r["ok"] is False


def test_origin_guard_blocks_cross_site():
    cross = client.post("/api/config", headers={"sec-fetch-site": "cross-site"}, json={"boards": []})
    assert cross.status_code == 403
    bad = client.post("/api/config", headers={"origin": "http://evil.example"}, json={"boards": []})
    assert bad.status_code == 403


def test_origin_guard_blocks_same_site_cross_port():
    # A page on another localhost PORT is same-site but a different origin. The old
    # hostname-only check let this through; full-origin matching must reject it.
    r1 = client.post("/api/config", headers={"sec-fetch-site": "same-site"}, json={"boards": []})
    assert r1.status_code == 403
    r2 = client.post("/api/config", headers={"origin": f"http://127.0.0.1:{DEFAULT_PORT + 1}"}, json={"boards": []})
    assert r2.status_code == 403


def test_origin_guard_allows_same_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("SUUR_THINGS_CONFIG", str(tmp_path / "board.json"))
    ok = client.post(
        "/api/config",
        headers={"sec-fetch-site": "same-origin", "origin": f"http://127.0.0.1:{DEFAULT_PORT}"},
        json={"boards": []},
    )
    assert ok.status_code == 200 and ok.json()["ok"] is True


def test_trusted_host_rejects_foreign_host():
    # DNS-rebinding sends the attacker's hostname as Host; reject it on reads too.
    r = client.get("/api/state", headers={"host": "evil.example"})
    assert r.status_code == 400


def test_trusted_host_allows_localhost():
    for h in ("127.0.0.1", "localhost", f"127.0.0.1:{DEFAULT_PORT}"):
        r = client.get("/api/state", headers={"host": h})
        assert r.status_code == 200


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


def test_priority_levels_cleaning(tmp_path, monkeypatch):
    monkeypatch.setenv("SUUR_THINGS_CONFIG", str(tmp_path / "board.json"))
    import importlib

    from suur_things_mcp import config as cfg
    importlib.reload(cfg)
    saved = cfg.save({"priority_levels": [
        {"label": "  P1  ", "tags": [" Urgent ", "P1", "P1", None, 3, ""]},  # trim, dedup, drop junk
        {"tags": ["P2"]},                                                    # label defaults to P2
        "not-a-dict",                                                        # skipped
        {"label": "x" * 80, "tags": "notalist"},                            # label capped, tags->[]
    ]})
    pl = saved["priority_levels"]
    assert len(pl) == 3  # the "not-a-dict" entry is dropped
    assert pl[0] == {"label": "P1", "tags": ["Urgent", "P1"]}
    assert pl[1]["label"] == "P2" and pl[1]["tags"] == ["P2"]  # blank label -> default P2
    assert len(pl[2]["label"]) == 40 and pl[2]["tags"] == []   # label capped, non-list tags -> []


def test_priority_levels_merge_isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SUUR_THINGS_CONFIG", str(tmp_path / "board.json"))
    import importlib

    from suur_things_mcp import config as cfg
    importlib.reload(cfg)
    cfg.set_link("ILTY", "project", str(tmp_path))
    cfg.merge({"priority_levels": [{"label": "P1", "tags": ["Now"]}]})
    # priority_levels save must not wipe links, and vice versa.
    assert "ILTY" in cfg.load()["links"]
    assert cfg.load()["priority_levels"][0]["tags"] == ["Now"]
    cfg.merge({"boards": [{"id": "b", "name": "B", "columns": ["X"]}]})
    assert cfg.load()["priority_levels"][0]["tags"] == ["Now"]  # boards save preserved levels


def test_area_prefs_default_and_merge_isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SUUR_THINGS_CONFIG", str(tmp_path / "board.json"))
    import importlib

    from suur_things_mcp import config as cfg
    importlib.reload(cfg)
    assert cfg.area_rollup("any-uuid") is True  # default on, even when unset
    cfg.set_link("ILTY", "project", str(tmp_path))
    cfg.merge({"area_prefs": {"AREA1": {"rollup": False}, "bad": "x"}})
    assert cfg.area_rollup("AREA1") is False  # explicit off respected
    assert cfg.area_rollup("AREA2") is True   # untouched area still defaults on
    assert "ILTY" in cfg.load()["links"]      # didn't clobber other sections
    assert "bad" not in cfg.load()["area_prefs"]  # malformed entry dropped


@pytest.mark.skipif(not _things_available(), reason="Things database not available")
def test_area_rollup_off_shows_only_loose_todos():
    # With rollup off, an area returns only its loose to-dos (no project_title),
    # never tasks pulled from its projects.
    from suur_things_mcp import reads as r
    for a in r.areas():
        on = r.list_items(a["uuid"], rollup=True)
        if any(i.get("project_title") for i in on["items"]):
            off = r.list_items(a["uuid"], rollup=False)
            assert off["rollup"] is False
            assert not any(i.get("project_title") for i in off["items"])
            assert len(off["items"]) <= len(on["items"])
            return
    pytest.skip("no area with in-project tasks in this database")


@pytest.mark.skipif(not _things_available(), reason="Things database not available")
def test_area_view_rolls_up_in_project_tasks():
    # An area should surface tasks living inside its projects, grouped by project,
    # not just its loose to-dos. Find an area with at least one project task.
    from suur_things_mcp import reads as r
    sb = r.sidebar()
    target = None
    for a in sb["areas"]:
        items = r.list_items(a["uuid"])["items"]
        if any(i.get("project_title") for i in items):
            target = (a, items)
            break
    if not target:
        pytest.skip("no area with in-project tasks in this database")
    _area, items = target
    in_project = [i for i in items if i.get("project_title")]
    assert in_project, "area view should include tasks from its projects"
    # every rolled-up task carries a project_title so the renderer can group it
    assert all(i.get("project_title") for i in in_project)


def test_open_url_app_mode_prefers_chromium_then_falls_back(monkeypatch):
    from suur_things_mcp import dashboard as d
    calls = []
    monkeypatch.setattr(d.subprocess, "run", lambda args, **kw: calls.append(args))
    # A Chromium browser is installed -> launch it with --app=
    monkeypatch.setattr(d.os.path, "isdir", lambda p: "Google Chrome" in p)
    d._open_url("http://127.0.0.1:8765", app_mode=True)
    assert calls[-1] == ["open", "-na", "Google Chrome", "--args", "--app=http://127.0.0.1:8765"]
    # No Chromium browser -> plain open (normal tab)
    calls.clear()
    monkeypatch.setattr(d.os.path, "isdir", lambda p: False)
    d._open_url("http://127.0.0.1:8765", app_mode=True)
    assert calls[-1] == ["open", "http://127.0.0.1:8765"]
    # app_mode off always uses a plain open even if Chromium exists
    calls.clear()
    monkeypatch.setattr(d.os.path, "isdir", lambda p: True)
    d._open_url("http://127.0.0.1:8765", app_mode=False)
    assert calls[-1] == ["open", "http://127.0.0.1:8765"]


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
