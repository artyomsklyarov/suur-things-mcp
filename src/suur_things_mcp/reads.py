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


def find_by_exact_title(title: str) -> list[dict]:
    """Tasks whose title is EXACTLY ``title`` (uuid + creation time only).

    Used by the dashboard's quick-add to resolve a just-created item's UUID
    (the URL Scheme doesn't return it). This is a single exact-match read on
    one column — far cheaper than ``search()``'s ``LIKE '%...%'`` over
    title+notes+area joins, which the create flow polled up to a dozen times.
    Read-only and NOT ``immutable`` (we must see Things' fresh async write)."""
    # mode=ro (no immutable) on a fresh connection so each poll sees newly
    # committed rows. Degrade to [] if the DB is missing/locked (matches
    # things.py's tolerant behaviour) rather than raising into the caller.
    try:
        con = sqlite3.connect(_db_uri(immutable=False), uri=True)
    except sqlite3.Error:
        return []
    try:
        rows = con.execute(
            "SELECT uuid, creationDate FROM TMTask WHERE title = ? AND trashed = 0",
            (title,),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        con.close()
    return [{"uuid": u, "created": c or 0} for (u, c) in rows]


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

import re as _re

_URL_RE = _re.compile(r'https?://[^\s<>"\)]+')


def _first_url(item: dict) -> str | None:
    """First http(s) URL found in the title or notes (for the dashboard card view)."""
    m = _URL_RE.search((item.get("title") or "") + "\n" + (item.get("notes") or ""))
    return m.group(0) if m else None


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
        "link": _first_url(item),
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


def _db_uri(immutable: bool) -> str:
    """Read-only SQLite URI for the Things DB, with the path properly quoted so a
    path containing spaces/?/# can't break the URI. ``immutable`` for a stable
    snapshot (counts); leave it off when you must see Things' fresh writes."""
    from urllib.parse import quote

    flags = "mode=ro&immutable=1" if immutable else "mode=ro"
    return f"file:{quote(_db_path())}?{flags}"


def _project_progress() -> dict[str, float]:
    """uuid -> completion ratio (0..1) for projects, read straight from the DB.

    things.py doesn't expose the cached leaf-action counts, so we read the two
    columns Things itself maintains. Opened read-only + immutable so we never
    contend with the app's writes.
    """
    uri = _db_uri(immutable=True)
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


def list_items(list_id: str, completed_limit: int = 50, rollup: bool = True) -> dict:
    """To-dos for a sidebar selection: a built-in list, an area, or a project.

    `kind` tells the UI how to group: built-in lists group by project, a project
    groups by heading, an area is flat. `rollup` (areas only) folds in tasks from
    the area's projects; set False to show only the area's loose to-dos.
    """
    # Things' built-in lists (esp. Anytime/Someday) include *projects*, not just
    # to-dos. The dashboard renders a builtin list as task rows, so a project would
    # show up as a (checkbox-less, oddly grouped) "task". Keep these lists to-do-only;
    # projects remain reachable from the sidebar.
    if list_id == "logbook":
        return {"id": list_id, "kind": "builtin",
                "items": [_card(i) for i in logbook(limit=completed_limit) if i.get("type") == "to-do"]}
    if list_id in _BUILTIN_FNS:
        return {"id": list_id, "kind": "builtin",
                "items": [_card(i) for i in _BUILTIN_FNS[list_id]() if i.get("type") == "to-do"]}

    obj = get(list_id)
    notes = (obj.get("notes") or "").strip() if obj else ""
    if obj and obj.get("type") == "area":
        # Things shows an area as its *loose* to-dos only; tasks inside the area's
        # projects don't surface. We roll those in so an area is a true overview:
        # loose to-dos first, then each project's open tasks. The renderer groups
        # by project_title, so in-project tasks land under their project heading.
        # areas have no notes field in Things, but keep the shape uniform.
        loose = [_card(i) for i in todos(area_uuid=list_id)]
        in_project: list[dict] = []
        if rollup:
            proj_ids = {p["uuid"] for p in projects() if p.get("area") == list_id}
            if proj_ids:
                in_project = [_card(i) for i in todos(status="incomplete") if i.get("project") in proj_ids]
        return {"id": list_id, "kind": "area", "notes": notes, "rollup": rollup, "items": loose + in_project}
    return {"id": list_id, "kind": "project", "notes": notes, "items": [_card(i) for i in todos(project_uuid=list_id)]}


# --- Kanban board (tag-based status, browser-config inclusion) ------------

def _project_counts() -> dict[str, dict[str, int]]:
    """uuid -> {open, total} leaf-action counts for projects (read-only DB)."""
    uri = _db_uri(immutable=True)
    con = sqlite3.connect(uri, uri=True)
    try:
        rows = con.execute(
            "SELECT uuid, openUntrashedLeafActionsCount, untrashedLeafActionsCount "
            "FROM TMTask WHERE type=1 AND trashed=0"
        ).fetchall()
    finally:
        con.close()
    return {u: {"open": o or 0, "total": t or 0} for (u, o, t) in rows}


def board_cards(board: dict) -> list[dict]:
    """High-level cards for a project board: one per included project/area.

    Each card is an overview (progress + open count), not a task. Areas
    aggregate their projects' counts. Placement into columns is the caller's
    job (it lives in the board config, not in Things).
    """
    counts = _project_counts()
    project_by_id = {p["uuid"]: p for p in projects()}
    area_by_id = {a["uuid"]: a for a in areas()}
    project_area = {p["uuid"]: p.get("area") for p in projects()}

    def _ratio(open_c: int, total: int) -> float:
        return round((total - open_c) / total, 3) if total else 0.0

    cards: list[dict] = []
    for pid in board.get("include_projects") or []:
        p = project_by_id.get(pid)
        if not p:
            continue
        c = counts.get(pid, {"open": 0, "total": 0})
        notes = (p.get("notes") or "").strip()
        cards.append({
            "kind": "project", "id": pid, "title": p["title"],
            "area_title": p.get("area_title"),
            "desc": notes[:160] + ("…" if len(notes) > 160 else ""),
            "open": c["open"], "total": c["total"], "progress": _ratio(c["open"], c["total"]),
        })
    for aid in board.get("include_areas") or []:
        a = area_by_id.get(aid)
        if not a:
            continue
        open_sum = total_sum = 0
        for pid, area_of in project_area.items():
            if area_of == aid:
                c = counts.get(pid, {"open": 0, "total": 0})
                open_sum += c["open"]
                total_sum += c["total"]
        cards.append({
            "kind": "area", "id": aid, "title": a["title"], "area_title": None,
            "open": open_sum, "total": total_sum, "progress": _ratio(open_sum, total_sum),
        })
    return cards


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
