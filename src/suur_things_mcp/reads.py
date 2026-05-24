"""Read layer over the local Things SQLite database (via the ``things.py`` lib).

Reads are safe and direct: ``things.py`` opens the database read-only and
understands every schema quirk (Today/Anytime/Someday buckets, repeating
templates, tag joins, date encodings). We never write here — see ``urlscheme``.

Optional env var ``THINGS_DB`` overrides the database path (useful for testing
against a backup copy).
"""

from __future__ import annotations

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
