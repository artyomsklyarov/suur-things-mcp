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

# Images Things itself can't hold. Stored as a browser-side overlay (like priority/
# timeblocks): metadata in board.json, bytes on disk under the config dir. Image
# mimes only; the id is a safe slug we generate (never derived from user input),
# so it can't be turned into a path-traversal token by the serving endpoint.
IMAGE_MIMES = {
    "image/png": "png", "image/jpeg": "jpg", "image/gif": "gif",
    "image/webp": "webp", "image/heic": "heic", "image/heif": "heif",
}
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")

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


def _clean_area_prefs(data: dict) -> dict[str, Any]:
    """Per-area view prefs (browser overlay), keyed by area UUID. Currently just
    ``rollup``: whether an area view folds in its projects' tasks (default true).
    Only stores entries that differ from the default, so the file stays small."""
    raw = data.get("area_prefs")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for uuid, v in raw.items():
        if isinstance(v, dict) and "rollup" in v:
            out[str(uuid)] = {"rollup": bool(v["rollup"])}
    return out


def _clean_priority_levels(data: dict) -> list[dict[str, Any]]:
    """Priority Levels overlay: an ordered list of levels (P1 first), each mapped
    to one or more *existing* Things tags. A task sits at the first level whose
    tags it carries; ``tags[0]`` is the canonical tag written back to Things when
    a task is dragged into that level. Unlike the Eisenhower ``priority`` overlay,
    the source of truth here is real Things tags, not a per-uuid browser map."""
    lst = data.get("priority_levels")
    if not isinstance(lst, list):
        return []
    out: list[dict[str, Any]] = []
    for i, e in enumerate(lst):
        if not isinstance(e, dict):
            continue
        label = (str(e.get("label")).strip()[:40] if e.get("label") else "") or f"P{i + 1}"
        raw_tags = e.get("tags")
        tags: list[str] = []
        if isinstance(raw_tags, list):
            for t in raw_tags:
                if not isinstance(t, str):
                    continue
                t = t.strip()[:100]
                if t and t not in tags:
                    tags.append(t)
        out.append({"label": label, "tags": tags})
        if len(out) >= 8:  # sane cap; UI uses 4
            break
    return out


def _clean_timeblocks(data: dict) -> dict[str, Any]:
    """Dashboard-only day-timeline placements: {uuid: {date, start "HH:MM", mins}}.
    Never written to Things — purely a browser overlay like `priority`."""
    tb = data.get("timeblocks")
    if not isinstance(tb, dict):
        return {}
    out: dict[str, Any] = {}
    for k, v in tb.items():
        if not isinstance(v, dict):
            continue
        date, start = str(v.get("date", "")).strip(), str(v.get("start", "")).strip()
        try:
            mins = int(v.get("mins", 30))
        except (TypeError, ValueError):
            mins = 30
        if date and start:
            out[str(k)] = {"date": date, "start": start, "mins": max(5, min(mins, 1440))}
    return out


def _clean_attachments(data: dict) -> dict[str, Any]:
    """Image attachments overlay: {itemUuid: [{id, mime, name, caption, added}]}.

    Never written to Things. Bytes live on disk; only metadata is kept here. Drops
    entries with an unsafe id or a non-image mime."""
    raw = data.get("attachments")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for uuid, lst in raw.items():
        if not isinstance(lst, list):
            continue
        clean = []
        for e in lst:
            if not isinstance(e, dict):
                continue
            aid = str(e.get("id") or "").strip()
            mime = str(e.get("mime") or "").strip().lower()
            if not _SAFE_ID.match(aid) or mime not in IMAGE_MIMES:
                continue
            cap = e.get("caption")
            clean.append({
                "id": aid,
                "mime": mime,
                "name": (str(e.get("name")).strip()[:200] or "image") if e.get("name") else "image",
                "caption": str(cap).strip()[:500] if cap and str(cap).strip() else None,
                "added": str(e.get("added")).strip() if e.get("added") else None,
            })
        if clean:
            out[str(uuid)] = clean
    return out


def _clean(data: dict) -> dict[str, Any]:
    priority = data.get("priority")
    priority = (
        {str(k): str(v) for k, v in priority.items() if str(v) in QUADRANTS}
        if isinstance(priority, dict)
        else {}
    )
    link_table = _clean_links(data)
    prefs = _clean_prefs(data)
    tb = _clean_timeblocks(data)
    att = _clean_attachments(data)
    plevels = _clean_priority_levels(data)
    aprefs = _clean_area_prefs(data)
    common = {"priority": priority, "links": link_table, "prefs": prefs,
              "timeblocks": tb, "attachments": att, "priority_levels": plevels,
              "area_prefs": aprefs}
    # New shape: {"boards": [...]}.
    if isinstance(data.get("boards"), list) and data["boards"]:
        boards = [_clean_board(b) for b in data["boards"] if isinstance(b, dict)]
        return {"boards": boards, **common}
    # Legacy flat shape: {columns, include_areas, include_projects} → one board.
    if any(k in data for k in ("columns", "include_areas", "include_projects")):
        legacy = {**data, "id": data.get("id") or "default", "name": data.get("name") or "Project Board"}
        return {"boards": [_clean_board(legacy)], **common}
    return {"boards": [_default_board()], **common}


def _fresh() -> dict[str, Any]:
    return {"boards": [_default_board()], "priority": {}, "links": {}, "prefs": {},
            "timeblocks": {}, "attachments": {}, "priority_levels": [], "area_prefs": {}}


def area_rollup(area_uuid: str) -> bool:
    """Whether an area view folds in its projects' tasks. Default true."""
    pref = load().get("area_prefs", {}).get(str(area_uuid))
    return pref.get("rollup", True) if isinstance(pref, dict) else True


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
    for key in ("boards", "priority", "links", "prefs", "timeblocks", "attachments",
                "priority_levels", "area_prefs"):
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


# --- Image attachments (browser-side overlay; bytes on disk) --------------

def _attach_dir() -> Path:
    """Directory holding attachment bytes, alongside board.json (never in a repo)."""
    return _path().parent / "attachments"


def attachments() -> dict[str, Any]:
    return load().get("attachments", {})


def attachment_meta(item_uuid: str, att_id: str) -> dict[str, Any] | None:
    for a in attachments().get(str(item_uuid), []):
        if a.get("id") == att_id:
            return a
    return None


def attachment_path(item_uuid: str, meta: dict) -> Path:
    """On-disk path for an attachment. Built only from a stored metadata record and
    validated ids/mimes — never from request input — so it cannot escape the dir."""
    ext = IMAGE_MIMES.get(meta.get("mime", ""), "bin")
    return _attach_dir() / str(item_uuid) / f"{meta['id']}.{ext}"


def save_attachment(item_uuid: str, data: bytes, mime: str, name: str,
                    caption: str | None = None) -> dict[str, Any]:
    """Write image bytes to disk + record metadata. Returns the new metadata entry.

    Raises ValueError on a non-image mime. The id is server-generated (uuid4), so
    the serving path can never be attacker-controlled."""
    mime = (mime or "").strip().lower()
    if mime not in IMAGE_MIMES:
        raise ValueError(f"unsupported image type: {mime!r}")
    import datetime
    meta = {
        "id": uuid.uuid4().hex,
        "mime": mime,
        "name": (str(name).strip()[:200] or "image") if name else "image",
        "caption": str(caption).strip()[:500] if caption and str(caption).strip() else None,
        "added": datetime.date.today().isoformat(),
    }
    path = attachment_path(item_uuid, meta)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    cfg = load()
    table = cfg.setdefault("attachments", {})
    table.setdefault(str(item_uuid), []).append(meta)
    save(cfg)
    return meta


def note_ref_url(path: str) -> str:
    """The `file://` URL we drop into a task's notes for an attachment."""
    from urllib.parse import quote
    return f"file://{quote(path)}"


def note_ref_line(name: str, path: str) -> str:
    """Notes line appended for an attachment so the Things app shows there's an image
    (Things can't render the image itself, but linkifies the file:// URL into a
    tap-to-open reference). The leading marker makes the attachment obvious in Things."""
    return f"🖼 Image attached: {name} — {note_ref_url(path)}"


def remove_attachment(item_uuid: str, att_id: str) -> bool:
    """Delete an attachment's bytes + metadata. Returns True if something was removed."""
    meta = attachment_meta(item_uuid, att_id)
    if not meta:
        return False
    try:
        attachment_path(item_uuid, meta).unlink(missing_ok=True)
    except OSError:
        pass
    cfg = load()
    table = cfg.get("attachments", {})
    if str(item_uuid) in table:
        table[str(item_uuid)] = [a for a in table[str(item_uuid)] if a.get("id") != att_id]
        if not table[str(item_uuid)]:
            table.pop(str(item_uuid))
        save(cfg)
    return True


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
