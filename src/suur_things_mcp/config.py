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
import re
import uuid
from pathlib import Path
from typing import Any

DEFAULT_COLUMNS = ["Backlog", "In Progress", "On Hold", "Done"]
QUADRANTS = {"do", "schedule", "delegate", "eliminate"}

# Accept "owner/repo", an https github URL, or a git@github.com SSH url; capture "owner/repo".
_GITHUB_RE = re.compile(r"^(?:https?://github\.com/|git@github\.com:)?([\w.-]+/[\w.-]+?)(?:\.git)?/?$")


def _normalize_repo(path: Any) -> str | None:
    if not path:
        return None
    # Strip surrounding quotes/whitespace — pasted paths often arrive shell-quoted
    # (e.g. '/Users/.../My Folder'). Without this they look relative and realpath
    # would wrongly prepend the process cwd.
    s = str(path).strip().strip("'\"").strip()
    if not s:
        return None
    return os.path.normcase(os.path.realpath(os.path.expanduser(s)))


def _normalize_github(value: Any) -> str | None:
    if not value:
        return None
    m = _GITHUB_RE.match(str(value).strip())
    return m.group(1) if m else None


def _clean_link_entry(repo_entry: Any) -> dict[str, Any] | None:
    if not isinstance(repo_entry, dict):
        return None
    repo = _normalize_repo(repo_entry.get("repo"))
    if not repo:
        return None
    label = repo_entry.get("label")
    return {
        "repo": repo,
        "github": _normalize_github(repo_entry.get("github")),
        "label": str(label).strip() if label else None,
    }


def _clean_links(data: dict) -> dict[str, Any]:
    """Normalize the link table. Each item (project/area) holds a LIST of repos.

    Accepts the new shape ({"repos": [...]}) and a legacy single-repo entry; repos
    are de-duplicated by normalized path (last write wins).
    """
    raw = data.get("links")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for key, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind") if entry.get("kind") in ("project", "area") else "project"
        raw_repos = entry.get("repos")
        if not isinstance(raw_repos, list) and entry.get("repo"):  # legacy single repo
            raw_repos = [{"repo": entry.get("repo"), "github": entry.get("github"), "label": entry.get("label")}]
        by_path: dict[str, dict] = {}
        for r in raw_repos or []:
            cleaned = _clean_link_entry(r)
            if cleaned:
                by_path[cleaned["repo"]] = cleaned  # dedup by path
        if by_path:
            out[str(key)] = {"kind": kind, "repos": list(by_path.values())}
    return out


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


def _clean_prefs(data: dict) -> dict[str, Any]:
    p = data.get("prefs")
    if not isinstance(p, dict):
        return {}
    return {k: str(p[k]).strip() for k in ("editor", "terminal") if p.get(k) and str(p[k]).strip()}


def _clean(data: dict) -> dict[str, Any]:
    priority = data.get("priority")
    priority = (
        {str(k): str(v) for k, v in priority.items() if str(v) in QUADRANTS}
        if isinstance(priority, dict)
        else {}
    )
    link_table = _clean_links(data)
    prefs = _clean_prefs(data)
    # New shape: {"boards": [...]}.
    if isinstance(data.get("boards"), list) and data["boards"]:
        boards = [_clean_board(b) for b in data["boards"] if isinstance(b, dict)]
        return {"boards": boards, "priority": priority, "links": link_table, "prefs": prefs}
    # Legacy flat shape: {columns, include_areas, include_projects} → one board.
    if any(k in data for k in ("columns", "include_areas", "include_projects")):
        legacy = {**data, "id": data.get("id") or "default", "name": data.get("name") or "Project Board"}
        return {"boards": [_clean_board(legacy)], "priority": priority, "links": link_table, "prefs": prefs}
    return {"boards": [_default_board()], "priority": priority, "links": link_table, "prefs": prefs}


def _fresh() -> dict[str, Any]:
    return {"boards": [_default_board()], "priority": {}, "links": {}, "prefs": {}}


def prefs() -> dict[str, Any]:
    return load().get("prefs", {})


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


# --- Repo links (project/area ↔ one or more git repos) --------------------

def links() -> dict[str, Any]:
    return load().get("links", {})


def set_link(item_uuid: str, kind: str, repo: str, github: str | None = None,
             label: str | None = None) -> dict[str, Any]:
    """Add (or replace by path) a repo link for a project/area. Save normalizes."""
    cfg = load()
    table = cfg.setdefault("links", {})
    item = table.get(str(item_uuid)) or {"kind": kind, "repos": []}
    item["kind"] = kind if kind in ("project", "area") else item.get("kind", "project")
    norm = _normalize_repo(repo)
    item["repos"] = [r for r in item.get("repos", []) if _normalize_repo(r.get("repo")) != norm]
    item["repos"].append({"repo": repo, "github": github, "label": label})
    table[str(item_uuid)] = item
    return save(cfg)


def remove_link(item_uuid: str, repo: str | None = None) -> dict[str, Any]:
    """Remove one repo from an item (by path), or the whole item if repo is None."""
    cfg = load()
    table = cfg.get("links", {})
    if repo is None:
        table.pop(str(item_uuid), None)
    elif str(item_uuid) in table:
        norm = _normalize_repo(repo)
        item = table[str(item_uuid)]
        item["repos"] = [r for r in item.get("repos", []) if r.get("repo") != norm]
        if not item["repos"]:
            table.pop(str(item_uuid), None)
    return save(cfg)


def set_item_repos(item_uuid: str, kind: str, repos: list) -> dict[str, Any]:
    """Replace just one item's repo list (or remove it), preserving everything else.

    Loads fresh + saves, so it never clobbers other items, boards, or priority —
    this is what makes concurrent edits (CLI, another tab) safe.
    """
    cfg = load()
    table = cfg.setdefault("links", {})
    clean = [r for r in (repos or []) if isinstance(r, dict) and r.get("repo")]
    if clean:
        table[str(item_uuid)] = {
            "kind": kind if kind in ("project", "area") else "project",
            "repos": clean,
        }
    else:
        table.pop(str(item_uuid), None)
    return save(cfg)


def merge(partial: dict) -> dict[str, Any]:
    """Save only the top-level sections present in ``partial`` (boards/priority/links).

    Sections not included are read fresh from disk and preserved, so saving boards
    can't wipe links written by another writer, and vice versa.
    """
    cfg = load()
    for key in ("boards", "priority", "links", "prefs"):
        if key in partial:
            cfg[key] = partial[key]
    return save(cfg)


def link_for_path(path: str) -> dict[str, Any] | None:
    """The linked item whose repo equals/contains ``path`` (longest match wins).

    Returns {item_id, kind, repo: <repo entry>} or None. Stale repos (path no
    longer on disk) are skipped.
    """
    target = _normalize_repo(path)
    if not target:
        return None
    best: dict[str, Any] | None = None
    best_len = -1
    for item_id, item in load().get("links", {}).items():
        for r in item.get("repos", []):
            repo = r.get("repo")
            if not repo or not os.path.exists(repo):
                continue
            if target == repo or target.startswith(repo + os.sep):
                if len(repo) > best_len:
                    best_len = len(repo)
                    best = {"item_id": item_id, "kind": item.get("kind"), "repo": r}
    return best


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
