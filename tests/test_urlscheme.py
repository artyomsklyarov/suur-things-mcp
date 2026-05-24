"""Unit tests for the Things URL Scheme builder — pure, no Things required."""

from urllib.parse import parse_qs, urlsplit

import pytest

from suur_things_mcp import urlscheme
from suur_things_mcp.urlscheme import ThingsURLError, build_url, execute


def _query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query, keep_blank_values=True)


def test_build_url_basic():
    url = build_url("add", {"title": "Buy milk"})
    assert url == "things:///add?title=Buy%20milk"


def test_build_url_drops_none_keeps_empty():
    url = build_url("update", {"id": "x", "title": None, "deadline": ""})
    q = _query(url)
    assert "title" not in q
    assert q["deadline"] == [""]  # empty value clears the field in Things
    assert q["id"] == ["x"]


def test_build_url_booleans():
    url = build_url("add", {"title": "t", "completed": True, "reveal": False})
    q = _query(url)
    assert q["completed"] == ["true"]
    assert q["reveal"] == ["false"]


def test_build_url_encodes_newlines_and_commas():
    url = build_url("add", {"checklist-items": "a\nb", "tags": "work,home"})
    q = _query(url)
    assert q["checklist-items"] == ["a\nb"]
    assert q["tags"] == ["work,home"]
    assert "%0A" in url.upper()  # newline is percent-encoded on the wire


def test_build_url_special_characters():
    url = build_url("add", {"title": "Pay & file: 50% done?"})
    assert _query(url)["title"] == ["Pay & file: 50% done?"]


def test_execute_requires_token_for_update(monkeypatch):
    monkeypatch.setattr(urlscheme, "run_url", lambda url: None)
    with pytest.raises(ThingsURLError, match="auth token"):
        execute("update", {"id": "x", "completed": True}, auth_token=None)


def test_execute_injects_and_redacts_token(monkeypatch):
    ran = {}
    monkeypatch.setattr(urlscheme, "run_url", lambda url: ran.setdefault("url", url))
    returned = execute("update", {"id": "x"}, auth_token="SECRET123")
    # The real URL that ran carries the token...
    assert "SECRET123" in ran["url"]
    # ...but the value handed back to the model does not.
    assert "SECRET123" not in returned
    assert "***" in returned


def test_execute_add_needs_no_token(monkeypatch):
    monkeypatch.setattr(urlscheme, "run_url", lambda url: None)
    url = execute("add", {"title": "no token needed"}, auth_token=None)
    assert url.startswith("things:///add?")
