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
import re as _re
import sqlite3
import time
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

_URL_RE = _re.compile(r'https?://[^\s<>"\)]+')


def _days_since(stamp: Any) -> int | None:
    """Whole days since a things.py timestamp ("2026-08-28 10:11:58").

    None when the field is absent or unparseable, so callers can distinguish
    "no data" from "zero days old"."""
    if not stamp:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(stamp))
    except (TypeError, ValueError):
        return None
    return max(0, (datetime.datetime.now() - dt).days)



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
        # Age signals: cheap ints (not the raw stamps — get_item has those) so
        # every digest can see that an item is 400 days old without a second call.
        "age_days": _days_since(item.get("created")),
        "idle_days": _days_since(item.get("modified")),
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


# --- Staleness review -----------------------------------------------------
# A backlog of hundreds of open to-dos can't be reviewed item by item. These
# helpers slice it into DISJOINT cohorts, each of which takes one kind of
# decision, so a sweep is a handful of batch calls instead of hundreds of
# individual judgements. Raw SQL (not things.py) because this needs
# creationDate/userModificationDate arithmetic over every open row at once.

_AGE_BUCKETS = (
    (7, "< 1 week"),
    (30, "1w-1m"),
    (90, "1-3 months"),
    (180, "3-6 months"),
    (365, "6-12 months"),
    (10**6, "> 1 year"),
)


def _packed_today() -> int:
    """Today in Things' packed date format (11b year, 4b month, 5b day)."""
    d = datetime.date.today()
    return (d.year << 16) | (d.month << 12) | (d.day << 7)


def _unpack_date(packed: int | None) -> str | None:
    """Things' packed start/deadline int -> ISO date string, or None if unusable."""
    if not packed:
        return None
    try:
        return datetime.date((packed >> 16) & 0xFFF, (packed >> 12) & 0xF,
                             (packed >> 7) & 0x1F).isoformat()
    except ValueError:  # a malformed/zero component
        return None


def stale_cohorts(
    never_touched_days: int = 365,
    idle_days: int = 180,
    inbox_idle_days: int = 90,
    limit: int = 40,
) -> dict:
    """Slice the open backlog into disjoint review cohorts.

    Cohorts are assigned first-match-wins in the order below, so no item shows up
    in two queues and the counts add up to real, non-overlapping work:

      inbox_stale   — sitting in the Inbox past ``inbox_idle_days``. The Inbox is
                      meant to be transient; these have stopped being triaged.
      never_touched — created over ``never_touched_days`` ago and never edited
                      since (creation and modification stamps within a minute).
                      Timestamp equality is a review heuristic, not user intent.
      deferred      — scheduled for a date that has passed but still open. Their past date is a review signal; it does not explain why
                      they remain open.
      loose_stale   — no parent project and idle past ``idle_days``. Orphans.

    ``clusters`` groups whatever idle work remains by project, because cancelling
    one dead project retires dozens of to-dos in a single decision — far faster
    than reviewing them one at a time. ``dead_projects`` are open projects with no
    open to-do left at all.

    Each cohort is capped at ``limit`` items but reports its true ``total``.
    """
    con = sqlite3.connect(_db_uri(immutable=True), uri=True)
    try:
        rows = con.execute(
            "SELECT t.uuid, t.title, t.start, t.startDate, t.project, "
            "       t.creationDate, t.userModificationDate, p.title "
            "FROM TMTask t LEFT JOIN TMTask p ON p.uuid = t.project "
            "WHERE t.trashed=0 AND t.status=0 AND t.type=0"
        ).fetchall()
        dead = con.execute(
            "SELECT p.uuid, p.title FROM TMTask p "
            "WHERE p.trashed=0 AND p.status=0 AND p.type=1 AND NOT EXISTS ("
            "  SELECT 1 FROM TMTask t WHERE t.project=p.uuid AND t.trashed=0 AND t.status=0)"
        ).fetchall()
    finally:
        con.close()

    now = time.time()
    today_packed = _packed_today()
    today = datetime.date.today()

    cohorts: dict[str, list[dict]] = {
        "inbox_stale": [], "never_touched": [], "deferred": [], "loose_stale": [],
    }
    histogram = {label: 0 for _, label in _AGE_BUCKETS}
    remaining: list[dict] = []

    for uuid, title, start, start_date, project, created, modified, project_title in rows:
        age = int((now - created) / 86400) if created else None
        idle = int((now - modified) / 86400) if modified else None
        if age is not None:
            for cutoff, label in _AGE_BUCKETS:
                if age < cutoff:
                    histogram[label] += 1
                    break

        card = {"uuid": uuid, "title": title, "project_title": project_title,
                "age_days": age, "idle_days": idle}

        # First match wins — keeps the queues disjoint.
        if start == 0 and (idle or 0) > inbox_idle_days:
            cohorts["inbox_stale"].append(card)
        elif (age or 0) > never_touched_days and created and modified and abs(modified - created) < 60:
            cohorts["never_touched"].append(card)
        elif start_date and start_date < today_packed:
            scheduled = _unpack_date(start_date)
            days_late = (today - datetime.date.fromisoformat(scheduled)).days if scheduled else None
            cohorts["deferred"].append({**card, "scheduled": scheduled, "days_late": days_late})
        elif project is None and (idle or 0) > idle_days:
            cohorts["loose_stale"].append(card)
        elif (idle or 0) > idle_days:
            remaining.append(card)

    # Pass 4: what's left, grouped by project — one decision retires many items.
    by_project: dict[str, dict] = {}
    for card in remaining:
        name = card["project_title"] or "(no project)"
        slot = by_project.setdefault(name, {"project_title": name, "stale_count": 0,
                                            "oldest_idle_days": 0})
        slot["stale_count"] += 1
        slot["oldest_idle_days"] = max(slot["oldest_idle_days"], card["idle_days"] or 0)
    clusters = sorted(by_project.values(), key=lambda c: c["stale_count"], reverse=True)

    return {
        "counts": {
            "open_todos": len(rows),
            "reviewable": sum(len(v) for v in cohorts.values()) + len(remaining),
            **{k: len(v) for k, v in cohorts.items()},
            "clustered": len(remaining),
            "dead_projects": len(dead),
        },
        "age_histogram": histogram,
        "thresholds": {"never_touched_days": never_touched_days,
                       "idle_days": idle_days, "inbox_idle_days": inbox_idle_days},
        "cohorts": {
            name: {"total": len(items), "items": items[:limit]}
            for name, items in cohorts.items()
        },
        "clusters": clusters,
        "dead_projects": [{"uuid": u, "title": t} for u, t in dead],
    }
