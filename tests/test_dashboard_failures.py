"""Malformed local requests must fail without replacing overlay data."""

import base64
import json

import pytest
from test_dashboard import client

from suur_things_mcp import config, dashboard


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("SUUR_THINGS_CONFIG", str(tmp_path / "board.json"))
    monkeypatch.setenv("SUUR_THINGS_TOKEN_FILE", str(tmp_path / "no-token"))
    monkeypatch.setenv("THINGS_AUTH_TOKEN", "")
    config.save(
        {
            "prefs": {"editor": "cursor"},
            "links": {"project": {"kind": "project", "repos": [{"repo": str(tmp_path), "label": "Keep me"}]}},
        }
    )


@pytest.mark.parametrize("endpoint", ["/api/config", "/api/link"])
@pytest.mark.parametrize("payload", [[], None, "broken", 42])
def test_nonobject_requests_preserve_config(endpoint, payload):
    before = config._path().read_bytes()
    response = client.post(endpoint, content=json.dumps(payload), headers={"content-type": "application/json"})
    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert config._path().read_bytes() == before


@pytest.mark.parametrize("repos", ["not a list", {}, 42, [None], ["not an object"]])
def test_invalid_repo_lists_do_not_clear_existing_links(repos):
    before = config._path().read_bytes()
    response = client.post("/api/link", json={"item_id": "project", "repos": repos})
    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert config._path().read_bytes() == before


@pytest.mark.parametrize(
    "endpoint,owner,method,field",
    [
        ("/api/config", config, "load", "config"),
        ("/api/item?id=task", dashboard.reads, "item_detail", "item"),
        ("/api/board?id=default", config, "get_board", "columns"),
    ],
)
def test_read_errors_are_structured(endpoint, owner, method, field, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("fixture read unavailable")

    monkeypatch.setattr(owner, method, fail)
    response = client.get(endpoint)
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert field in response.json()
    assert "fixture read unavailable" in response.json()["error"]


def test_nonstring_attachment_mime_is_rejected():
    response = client.post(
        "/api/attach", json={"uuid": "task", "data": base64.b64encode(b"fixture").decode(), "mime": ["image/png"]}
    )
    assert response.status_code == 400
    assert response.json()["ok"] is False


def test_attachment_storage_failure_is_structured(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("fixture disk full")

    monkeypatch.setattr(config, "save_attachment", fail)
    response = client.post(
        "/api/attach", json={"uuid": "task", "data": base64.b64encode(b"fixture").decode(), "mime": "image/png"}
    )
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "fixture disk full" in response.json()["error"]


@pytest.mark.parametrize(
    "section", ["boards", "priority_levels", "priority", "links", "prefs", "timeblocks", "attachments", "area_prefs"]
)
def test_invalid_section_types_preserve_config(section):
    before = config._path().read_bytes()
    response = client.post("/api/config", json={section: "invalid"})
    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert config._path().read_bytes() == before
