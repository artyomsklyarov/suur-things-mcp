"""Agent output is untrusted; no real agent processes are invoked here."""

import json
import subprocess

import pytest

from suur_things_mcp import organize


@pytest.mark.parametrize(
    "tags, expected",
    [
        ("urgent", ["urgent"]),
        (12, []),
        (True, []),
        ({"urgent": 1}, []),
        ([None, " urgent ", "urgent", 2], ["urgent"]),
    ],
)
def test_malformed_tags_do_not_break_or_invent_suggestions(tags, expected):
    result = organize.parse_suggestions(json.dumps([{"uuid": "task", "tags": tags}]), "codex")
    assert result[0]["tags"] == expected


def test_code_fences_inside_notes_survive_parsing():
    notes = 'Run this example:\n```json\n{"ok": true}\n```'
    payload = [{"uuid": "task", "append_notes": notes}]
    result = organize.parse_suggestions("Here you go:\n```json\n" + json.dumps(payload) + "\n```\nDone.", "codex")
    assert result[0]["append_notes"] == notes


def test_organizer_only_returns_unique_submitted_task_ids(monkeypatch):
    monkeypatch.setattr(organize, "_command", lambda *_: ["fake-agent"])
    monkeypatch.setattr(organize, "_login_path", lambda: "/fake/bin")
    payload = [
        {"uuid": "task", "suggested_title": "First"},
        {"uuid": "other", "suggested_title": "Unrelated"},
        {"uuid": "task", "suggested_title": "Duplicate"},
    ]
    monkeypatch.setattr(
        organize.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a[0], 0, json.dumps(payload), "")
    )
    result = organize.organize("Inbox", [{"uuid": "task", "title": "Original"}], [], "codex")
    assert [(r["uuid"], r["suggested_title"]) for r in result] == [("task", "First")]
