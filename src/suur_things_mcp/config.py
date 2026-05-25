"""Browser-side board configuration (multiple boards + planning overlays).

The "extra stuff that operates on top of Things, but lives only in the browser":
  - named project boards, each scoped to chosen areas/projects, with status
    columns and a per-board placement map (which column each project/area card
    sits in).
  - a priority overlay: which Eisenhower quadrant each Today task is in.

None of this is written back to Things (Things has no project-stage or quadrant
concept). Stored as JSON at ``$XDG_CONFIG_HOME/suur-things-mcp/board.json``
(falls back to ``~/.config/...``). Override with ``SUUR_THINGS_CONFIG`` for tests.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

DEFAULT_COLUMNS = ["Backlog", "In Progress", "On Hold", "Done"]
QUADRANTS = {"do", "schedule", "delegate", "eliminate"}


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
        "placements": {},
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
    placements = b.get("placements")
    if isinstance(placements, dict):
        # itemId -> column name (must be one of this board's columns)
        valid = set(board["columns"])
        board["placements"] = {
            str(k): str(v) for k, v in placements.items() if str(v) in valid
        }
    return board


def _clean(data: dict) -> dict[str, Any]:
    priority = data.get("priority")
    priority = (
        {str(k): str(v) for k, v in priority.items() if str(v) in QUADRANTS}
        if isinstance(priority, dict)
        else {}
    )
    # New shape: {"boards": [...]}.
    if isinstance(data.get("boards"), list) and data["boards"]:
        boards = [_clean_board(b) for b in data["boards"] if isinstance(b, dict)]
        return {"boards": boards, "priority": priority}
    # Legacy flat shape: {columns, include_areas, include_projects} → one board.
    if any(k in data for k in ("columns", "include_areas", "include_projects")):
        legacy = {**data, "id": data.get("id") or "default", "name": data.get("name") or "Project Board"}
        return {"boards": [_clean_board(legacy)], "priority": priority}
    return {"boards": [_default_board()], "priority": priority}


def _fresh() -> dict[str, Any]:
    return {"boards": [_default_board()], "priority": {}}


def load() -> dict[str, Any]:
    path = _path()
    if not path.exists():
        return _fresh()
    try:
        return _clean(json.loads(path.read_text()))
    except (json.JSONDecodeError, OSError):
        return _fresh()


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


# --- Auth token resolution ------------------------------------------------

def _token_path() -> Path:
    override = os.environ.get("SUUR_THINGS_TOKEN_FILE")
    if override:
        return Path(override)
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(Path.home(), ".config")
    return Path(base) / "suur-things-mcp" / "token"


def auth_token() -> str | None:
    """The Things URL Scheme auth token, for write-backs.

    Resolved from ``THINGS_AUTH_TOKEN`` first, then a private token file at
    ``$XDG_CONFIG_HOME/suur-things-mcp/token`` (outside any repo). Returns None
    if neither is set — callers then stay read-only.
    """
    env = os.environ.get("THINGS_AUTH_TOKEN")
    if env and env.strip():
        return env.strip()
    path = _token_path()
    if path.exists():
        try:
            return path.read_text().strip() or None
        except OSError:
            return None
    return None
