"""Browser-side board configuration (supports multiple saved boards).

The "extra stuff that operates on top of Things, but lives only in the browser":
named Kanban boards, each scoped to chosen areas/projects, with an ordered list
of status columns (each column is a Things tag name). Card status itself lives in
Things as tags — this file only holds the overlay.

Stored as JSON at ``$XDG_CONFIG_HOME/suur-things-mcp/board.json`` (falls back to
``~/.config/...``). Override with ``SUUR_THINGS_CONFIG`` for tests.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

DEFAULT_COLUMNS = ["Backlog", "In Progress", "On Hold", "Done"]


def _path() -> Path:
    override = os.environ.get("SUUR_THINGS_CONFIG")
    if override:
        return Path(override)
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(Path.home(), ".config")
    return Path(base) / "suur-things-mcp" / "board.json"


def _default_board(name: str = "Project Board") -> dict[str, Any]:
    # Stable id so the migrated/default board survives reloads (the UI assigns
    # random ids to boards it creates and persists immediately).
    return {
        "id": "default",
        "name": name,
        "columns": list(DEFAULT_COLUMNS),
        "include_areas": [],
        "include_projects": [],
    }


def _clean_board(b: dict) -> dict[str, Any]:
    board = _default_board(str(b.get("name") or "Untitled board"))
    if b.get("id"):
        board["id"] = str(b["id"])
    cols = b.get("columns")
    if isinstance(cols, list):
        board["columns"] = [str(c).strip() for c in cols if str(c).strip()]
    for key in ("include_areas", "include_projects"):
        vals = b.get(key)
        if isinstance(vals, list):
            board[key] = [str(v) for v in vals if v]
    return board


def _clean(data: dict) -> dict[str, Any]:
    # New shape: {"boards": [...]}.
    if isinstance(data.get("boards"), list) and data["boards"]:
        return {"boards": [_clean_board(b) for b in data["boards"] if isinstance(b, dict)]}
    # Legacy flat shape: {columns, include_areas, include_projects} → one board.
    if any(k in data for k in ("columns", "include_areas", "include_projects")):
        legacy = {**data, "id": data.get("id") or "default", "name": data.get("name") or "Project Board"}
        return {"boards": [_clean_board(legacy)]}
    return {"boards": [_default_board()]}


def load() -> dict[str, Any]:
    path = _path()
    if not path.exists():
        return {"boards": [_default_board()]}
    try:
        return _clean(json.loads(path.read_text()))
    except (json.JSONDecodeError, OSError):
        return {"boards": [_default_board()]}


def save(data: dict) -> dict[str, Any]:
    cfg = _clean(data or {})
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2))
    return cfg


def get_board(board_id: str) -> dict[str, Any] | None:
    for b in load()["boards"]:
        if b["id"] == board_id:
            return b
    return None
