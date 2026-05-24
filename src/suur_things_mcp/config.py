"""Browser-side board configuration.

This is the "extra stuff that operates on top of Things, but lives only in the
browser": which areas/projects appear on the Kanban board, and the ordered list
of status columns (each column is a Things tag name). Card status itself lives
in Things as tags — this file only holds the overlay.

Stored as JSON at ``$XDG_CONFIG_HOME/suur-things-mcp/board.json`` (falls back to
``~/.config/...``). Override with ``SUUR_THINGS_CONFIG`` for tests.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    # Each column is a Things tag name. A card sits in the column whose tag it
    # carries; included cards with none land in a leading "Unsorted" column.
    "columns": ["Backlog", "In Progress", "On Hold", "Done"],
    # UUIDs of areas / projects whose to-dos populate the board.
    "include_areas": [],
    "include_projects": [],
}


def _path() -> Path:
    override = os.environ.get("SUUR_THINGS_CONFIG")
    if override:
        return Path(override)
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(Path.home(), ".config")
    return Path(base) / "suur-things-mcp" / "board.json"


def _clean(data: dict) -> dict[str, Any]:
    cfg = {k: (v.copy() if isinstance(v, list) else v) for k, v in DEFAULTS.items()}
    cols = data.get("columns")
    if isinstance(cols, list):
        cfg["columns"] = [str(c).strip() for c in cols if str(c).strip()]
    for key in ("include_areas", "include_projects"):
        vals = data.get(key)
        if isinstance(vals, list):
            cfg[key] = [str(v) for v in vals if v]
    return cfg


def load() -> dict[str, Any]:
    path = _path()
    if not path.exists():
        return {k: (v.copy() if isinstance(v, list) else v) for k, v in DEFAULTS.items()}
    try:
        return _clean(json.loads(path.read_text()))
    except (json.JSONDecodeError, OSError):
        return {k: (v.copy() if isinstance(v, list) else v) for k, v in DEFAULTS.items()}


def save(data: dict) -> dict[str, Any]:
    cfg = _clean(data or {})
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2))
    return cfg
