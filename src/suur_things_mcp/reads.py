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
import sqlite3
from typing import Any

import things
import things.database as _thingsdb

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
        "status": item.get("status"),
        "type": item.get("type"),
        "project_title": item.get("project_title"),
        "heading_title": item.get("heading_title"),
        "area_title": item.get("area_title"),
        "deadline": item.get("deadline"),
        "start_date": item.get("start_date"),
        "start": item.get("start"),
        "tags": item.get("tags"),
        "has_notes": bool(item.get("notes")),
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


# --- Sidebar / navigation (powers the Things-style dashboard) -------------

def _db_path() -> str:
    return os.environ.get("THINGS_DB") or _thingsdb.DEFAULT_FILEPATH


def _project_progress() -> dict[str, float]:
    """uuid -> completion ratio (0..1) for projects, read straight from the DB.

    things.py doesn't expose the cached leaf-action counts, so we read the two
    columns Things itself maintains. Opened read-only + immutable so we never
    contend with the app's writes.
    """
    uri = f"file:{_db_path()}?mode=ro&immutable=1"
    con = sqlite3.connect(uri, uri=True)
    try:
        rows = con.execute(
            "SELECT uuid, openUntrashedLeafActionsCount, untrashedLeafActionsCount "
            "FROM TMTask WHERE type=1 AND trashed=0"
        ).fetchall()
    finally:
        con.close()
    out: dict[str, float] = {}
    for uuid, open_count, total in rows:
        total = total or 0
        out[uuid] = round((total - (open_count or 0)) / total, 3) if total else 0.0
    return out


# Built-in lists, in Things' sidebar order. icon is an emoji approximation.
_BUILTINS = [
    ("inbox", "Inbox", "\U0001F4E5", inbox),
    ("today", "Today", "⭐", today),
    ("upcoming", "Upcoming", "\U0001F4C5", upcoming),
    ("anytime", "Anytime", "\U0001F5C2️", anytime),
    ("someday", "Someday", "\U0001F5C4️", someday),
    ("logbook", "Logbook", "✅", None),
    ("trash", "Trash", "\U0001F5D1️", None),
]


def sidebar() -> dict:
    """The full navigation tree: built-in lists + areas with nested projects."""
    builtins = []
    for list_id, title, icon, fn in _BUILTINS:
        entry = {"id": list_id, "title": title, "icon": icon}
        # Only Inbox and Today show a count badge in Things.
        if list_id in ("inbox", "today") and fn is not None:
            entry["count"] = len(fn())
        builtins.append(entry)

    progress = _project_progress()
    by_area: dict[str | None, list[dict]] = {}
    for p in projects():
        if p.get("status") != "incomplete":
            continue
        by_area.setdefault(p.get("area"), []).append(
            {
                "uuid": p["uuid"],
                "title": p["title"],
                "progress": progress.get(p["uuid"], 0.0),
            }
        )

    area_tree = [
        {"uuid": a["uuid"], "title": a["title"], "projects": by_area.get(a["uuid"], [])}
        for a in areas()
    ]
    return {
        "builtins": builtins,
        "areas": area_tree,
        "arealess": by_area.get(None, []),
    }


_BUILTIN_FNS = {
    "inbox": inbox,
    "today": today,
    "upcoming": upcoming,
    "anytime": anytime,
    "someday": someday,
    "trash": trash,
}


def list_items(list_id: str, completed_limit: int = 50) -> dict:
    """To-dos for a sidebar selection: a built-in list, an area, or a project.

    `kind` tells the UI how to group: built-in lists group by project, a project
    groups by heading, an area is flat.
    """
    if list_id == "logbook":
        return {"id": list_id, "kind": "builtin", "items": [_card(i) for i in logbook(limit=completed_limit)]}
    if list_id in _BUILTIN_FNS:
        return {"id": list_id, "kind": "builtin", "items": [_card(i) for i in _BUILTIN_FNS[list_id]()]}

    obj = get(list_id)
    if obj and obj.get("type") == "area":
        return {"id": list_id, "kind": "area", "items": [_card(i) for i in todos(area_uuid=list_id)]}
    return {"id": list_id, "kind": "project", "items": [_card(i) for i in todos(project_uuid=list_id)]}


# --- Kanban board (tag-based status, browser-config inclusion) ------------

def _project_area_map() -> dict[str, str | None]:
    return {p["uuid"]: p.get("area") for p in projects()}


def kanban(config: dict) -> dict:
    """Build the Kanban board for the configured columns + included scope.

    Columns are Things tag names. A card lands in the first column whose tag it
    carries; included cards with no column tag go to a leading "Unsorted" column.
    """
    columns: list[str] = config.get("columns") or []
    include_projects = set(config.get("include_projects") or [])
    include_areas = set(config.get("include_areas") or [])
    project_area = _project_area_map()

    buckets: dict[str, list[dict]] = {c: [] for c in columns}
    unsorted: list[dict] = []

    for t in todos(status="incomplete"):
        proj = t.get("project")
        area = t.get("area")
        included = (
            proj in include_projects
            or area in include_areas
            or (proj is not None and project_area.get(proj) in include_areas)
        )
        if not included:
            continue
        tags = t.get("tags") or []
        column = next((c for c in columns if c in tags), None)
        (buckets[column] if column else unsorted).append(_card(t))

    out: list[dict] = []
    if unsorted:
        out.append({"name": None, "title": "Unsorted", "cards": unsorted})
    for c in columns:
        out.append({"name": c, "title": c, "cards": buckets[c]})
    return {"columns": out}


def item_detail(uuid: str) -> dict | None:
    """Full detail for the edit dialog: notes, tags, checklist, dates."""
    it = get(uuid)
    if not it:
        return None
    return {
        "uuid": it.get("uuid"),
        "title": it.get("title"),
        "notes": it.get("notes"),
        "status": it.get("status"),
        "start": it.get("start"),
        "start_date": it.get("start_date"),
        "deadline": it.get("deadline"),
        "tags": it.get("tags") or [],
        "project_title": it.get("project_title"),
        "checklist": [
            {"title": c.get("title"), "status": c.get("status")}
            for c in (it.get("checklist") or [])
        ],
    }


def tags_after_move(uuid: str, target_column: str | None, column_tags: set[str]) -> list[str]:
    """New tag set when moving a card to ``target_column``.

    Drops every column tag the card currently has and adds the target, leaving
    all non-status tags (e.g. SUUR, Errand) untouched. Empty list clears tags.
    """
    it = get(uuid)
    current = (it.get("tags") if it else None) or []
    kept = [t for t in current if t not in column_tags]
    if target_column:
        kept.append(target_column)
    return kept
