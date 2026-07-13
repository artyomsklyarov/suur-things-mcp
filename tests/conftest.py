"""Shared fixtures.

`things_db` builds a throwaway SQLite database with the real Things schema
(tests/things_schema.sql) and a small, known dataset, then points the read
layer at it. This is what lets reads.py be tested in CI (Linux, no Things):
before it, every data-route test silently skipped outside macOS+Things.
"""

from __future__ import annotations

import datetime
import sqlite3
import time
from pathlib import Path

import pytest

SCHEMA = (Path(__file__).parent / "things_schema.sql").read_text()

# Things' packed date format: 11 bits year, 4 bits month, 5 bits day, 7 zero bits.
def thingsdate(d: datetime.date) -> int:
    return (d.year << 16) | (d.month << 12) | (d.day << 7)


DB_VERSION_PLIST = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
    '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
    '<plist version="1.0">\n<integer>26</integer>\n</plist>\n'
)

TODAY = datetime.date.today()
YESTERDAY = TODAY - datetime.timedelta(days=1)
NEXT_WEEK = TODAY + datetime.timedelta(days=7)


def _task(uuid, title, *, type=0, status=0, start=1, trashed=0, project=None,
          area=None, start_date=None, deadline=None, notes="", stop_date=None,
          index=0, today_index=0):
    """Row dict for TMTask with the columns things.py cares about."""
    now = time.time()
    return {
        "uuid": uuid, "title": title, "type": type, "status": status,
        "start": start, "trashed": trashed, "project": project, "area": area,
        "startDate": start_date, "deadline": deadline, "notes": notes,
        "stopDate": stop_date, "creationDate": now, "userModificationDate": now,
        "index": index, "todayIndex": today_index, "leavesTombstone": 0,
        "notesSync": 0, "startBucket": 0,
    }


FIXTURE_TASKS = [
    # Inbox
    _task("todo-inbox", "Sort the mail", start=0),
    # Today: startDate = today, start = Anytime
    _task("todo-today", "Write the report", start=1,
          start_date=thingsdate(TODAY), notes="key notes", area="area-work"),
    # Overdue deadline, also lands in Today
    _task("todo-overdue", "Pay invoice", start=1,
          start_date=thingsdate(YESTERDAY), deadline=thingsdate(YESTERDAY)),
    # Upcoming
    _task("todo-upcoming", "Book flights", start=2, start_date=thingsdate(NEXT_WEEK)),
    # Anytime, inside a project
    _task("todo-inproj", "Draft outline", start=1, project="proj-book"),
    # Someday
    _task("todo-someday", "Learn woodworking", start=2),
    # Completed yesterday (logbook)
    _task("todo-done", "Ship v1", status=3, stop_date=time.time() - 3600),
    # Trashed
    _task("todo-trash", "Old junk", trashed=1),
    # Projects: one in an area with an open task, one with NO open next action
    _task("proj-book", "Write a book", type=1, area="area-work"),
    _task("proj-empty", "Stalled project", type=1),
    # A loose to-do directly in the area (for roll-up tests)
    _task("todo-loose", "Area loose task", start=1, area="area-work"),
]

FIXTURE_AREAS = [("area-work", "Work", 0)]
FIXTURE_TAGS = [("tag-urgent", "urgent", 0), ("tag-home", "home", 1)]
FIXTURE_TASKTAGS = [("todo-today", "tag-urgent")]
FIXTURE_CHECKLIST = [
    ("chk-1", "Chapter list", "todo-inproj", 0, 0),
]


def build_things_db(path: str) -> None:
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.execute("INSERT INTO Meta (key, value) VALUES ('databaseVersion', ?)",
                (DB_VERSION_PLIST,))
    for t in FIXTURE_TASKS:
        cols = ", ".join(f'"{c}"' for c in t)
        marks = ", ".join("?" for _ in t)
        con.execute(f"INSERT INTO TMTask ({cols}) VALUES ({marks})", list(t.values()))
    con.executemany(
        'INSERT INTO TMArea (uuid, title, "index") VALUES (?, ?, ?)', FIXTURE_AREAS)
    con.executemany(
        'INSERT INTO TMTag (uuid, title, "index") VALUES (?, ?, ?)', FIXTURE_TAGS)
    con.executemany(
        "INSERT INTO TMTaskTag (tasks, tags) VALUES (?, ?)", FIXTURE_TASKTAGS)
    con.executemany(
        'INSERT INTO TMChecklistItem (uuid, title, task, "index", status) '
        "VALUES (?, ?, ?, ?, ?)", FIXTURE_CHECKLIST)
    con.commit()
    con.close()


@pytest.fixture
def things_db(tmp_path, monkeypatch):
    """A fake Things database with a known dataset; reads.py is pointed at it."""
    db = tmp_path / "main.sqlite"
    build_things_db(str(db))
    from suur_things_mcp import reads

    monkeypatch.setenv("THINGS_DB", str(db))
    # reads._DB is captured at import time; re-point it for this test.
    monkeypatch.setattr(reads, "_DB", str(db))
    return str(db)
