"""Read layer over the local Things SQLite database (via the ``things.py`` lib).

Reads are safe and direct: ``things.py`` opens the database read-only and
understands every schema quirk (Today/Anytime/Someday buckets, repeating
templates, tag joins, date encodings). We never write here — see ``urlscheme``.

Optional env var ``THINGS_DB`` overrides the database path (useful for testing
against a backup copy).
"""

from __future__ import annotations

import datetime
import os
from typing import Any

import things

_DB = os.environ.get("THINGS_DB") or None


def _kw(**extra: Any) -> dict:
    """Common kwargs for things.py calls, threading the optional db path."""
    params: dict[str, Any] = {}
    if _DB:
        params["filepath"] = _DB
    params.update({k: v for k, v in extra.items() if v is not None})
    return params


# --- Built-in lists -------------------------------------------------------

def inbox() -> list[dict]:
    return things.inbox(**_kw())


def today() -> list[dict]:
    return things.today(**_kw())


def upcoming() -> list[dict]:
    return things.upcoming(**_kw())


def anytime() -> list[dict]:
    return things.anytime(**_kw())


def someday() -> list[dict]:
    return things.someday(**_kw())


def logbook(limit: int = 50) -> list[dict]:
    # `last` understands relative windows ("7d"); we cap with a count instead.
    items = things.logbook(**_kw())
    return items[: max(0, limit)] if limit else items


def trash() -> list[dict]:
    return things.trash(**_kw())


def deadlines() -> list[dict]:
    return things.deadlines(**_kw())


# --- Queries --------------------------------------------------------------

def search(query: str) -> list[dict]:
    return things.search(query, **_kw())


def todos(
    project_uuid: str | None = None,
    area_uuid: str | None = None,
    tag: str | None = None,
    status: str | None = None,
    start: str | None = None,
) -> list[dict]:
    """Flexible to-do query.

    status: 'incomplete' (default in Things) | 'completed' | 'canceled'
    start:  'Inbox' | 'Anytime' | 'Someday'
    """
    return things.todos(
        **_kw(
            project=project_uuid,
            area=area_uuid,
            tag=tag,
            status=status,
            start=start,
        )
    )


def projects(include_items: bool = False) -> list[dict]:
    return things.projects(**_kw(include_items=include_items))


def areas(include_items: bool = False) -> list[dict]:
    return things.areas(**_kw(include_items=include_items))


def tags(include_items: bool = False) -> list[dict]:
    return things.tags(**_kw(include_items=include_items))


def get(uuid: str) -> dict | None:
    """Full detail for any item (to-do, project, area, or tag) by UUID.

    For to-dos and projects this includes notes and checklist items.
    """
    return things.get(uuid, **_kw())


# --- Digest ---------------------------------------------------------------

def _card(item: dict) -> dict:
    """Compact projection of a to-do for token-cheap digests/boards."""
    return {
        "uuid": item.get("uuid"),
        "title": item.get("title"),
        "project_title": item.get("project_title"),
        "area_title": item.get("area_title"),
        "deadline": item.get("deadline"),
        "start_date": item.get("start_date"),
        "tags": item.get("tags"),
    }


def overview(recent_completed: int = 10) -> dict:
    """One-call situational digest of the whole Things system.

    Replaces ~10 separate read calls. Pure composition over the queries above,
    so it inherits things.py's read-only, lock-tolerant access.
    """
    inbox_items = inbox()
    today_items = today()
    upcoming_items = upcoming()
    anytime_items = anytime()
    someday_items = someday()
    recent = logbook(limit=recent_completed)
    all_projects = projects()

    # Projects with no open next action: no incomplete to-do points at them.
    incomplete = todos(status="incomplete")
    projects_with_action = {t.get("project") for t in incomplete if t.get("project")}
    no_next_action = [
        {"uuid": p["uuid"], "title": p.get("title"), "area_title": p.get("area_title")}
        for p in all_projects
        if p.get("status") == "incomplete" and p["uuid"] not in projects_with_action
    ]

    # Overdue: incomplete items whose deadline is before today.
    today_str = datetime.date.today().isoformat()
    overdue = [
        _card(t) for t in deadlines() if t.get("deadline") and t["deadline"] < today_str
    ]

    return {
        "counts": {
            "inbox": len(inbox_items),
            "today": len(today_items),
            "upcoming": len(upcoming_items),
            "anytime": len(anytime_items),
            "someday": len(someday_items),
            "projects": len([p for p in all_projects if p.get("status") == "incomplete"]),
            "overdue": len(overdue),
            "projects_without_next_action": len(no_next_action),
        },
        "today": [_card(t) for t in today_items],
        "overdue": overdue,
        "projects_without_next_action": no_next_action,
        "recent_completed": [_card(t) for t in recent],
    }


def board() -> dict:
    """Kanban columns for the dashboard: list name -> compact cards."""
    return {
        "inbox": [_card(t) for t in inbox()],
        "today": [_card(t) for t in today()],
        "upcoming": [_card(t) for t in upcoming()],
        "anytime": [_card(t) for t in anytime()],
        "someday": [_card(t) for t in someday()],
    }
