"""Things-style dashboard: lists, project boards, and a priority square.

One two-pane UI. The sidebar holds Things' built-in lists, a Priority Square
(Eisenhower matrix over Today), saved project boards, and your areas with nested
projects. The main panel shows whatever you select.

  - Lists/areas/projects → Things-style grouped list.
  - A project board → a portfolio Kanban whose cards are the included
    projects/areas, staged into columns. Click a card to open it.
  - Priority Square → drag today's tasks into Eisenhower quadrants.

Project-stage placement and priority quadrants are browser-side overlays (stored
in board.json, never written to Things), so dragging needs no auth token. Editing
a task's fields writes to Things via the URL Scheme and needs THINGS_AUTH_TOKEN.

Run:
  - `suur-things-mcp dashboard`  → foreground (CLI), opens your browser
  - the `open_dashboard` MCP tool → background daemon thread, returns the URL
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import shutil
import socket
import subprocess
import threading
from typing import Any
import urllib.request

import uvicorn
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.routing import Route

import time
import uuid as _uuid

from . import config as boardcfg
from . import organize as organizer
from . import reads
from .urlscheme import ThingsURLError, execute

# In-memory organize jobs (single uvicorn worker). job_id -> dict.
_ORGANIZE_JOBS: dict[str, dict] = {}
_ORGANIZE_TTL = 1800  # evict finished jobs after 30 min
# Guards the dedupe / global-cap / insert check-then-act, which runs in a
# threadpool worker and races against the background _work() thread's updates.
_ORGANIZE_LOCK = threading.Lock()

_ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
_GITHUB_SLUG_RE = re.compile(r"^[\w.-]+/[\w.-]+$")


class _OriginGuard(BaseHTTPMiddleware):
    """Reject cross-origin POSTs. 127.0.0.1 binding + TrustedHostMiddleware stop
    DNS-rebinding, but a page served from a *different localhost port* is a distinct
    origin yet the same host — so a hostname-only check would wave it through and let
    it write config or launch local apps. We compare the FULL origin (scheme+host+
    port) against this server's own. ``sec-fetch-site`` is checked too: browsers
    always send it and an attacker page cannot forge it, so anything but
    ``same-origin`` (including same-site cross-port) is rejected. Both headers absent
    means a non-browser local client, which already has local execution — allowed.
    """

    def __init__(self, app, allowed_origins: set[str]):
        super().__init__(app)
        self._allowed = allowed_origins

    async def dispatch(self, request: Request, call_next):
        if request.method == "POST":
            sfs = request.headers.get("sec-fetch-site")
            if sfs is not None and sfs != "same-origin":
                return JSONResponse({"ok": False, "error": "cross-origin blocked"}, status_code=403)
            origin = request.headers.get("origin")
            if origin is not None and origin not in self._allowed:
                return JSONResponse({"ok": False, "error": "bad origin"}, status_code=403)
        return await call_next(request)

DEFAULT_PORT = 8765
_running: dict[str, Any] = {}


def _auth_token() -> str | None:
    return boardcfg.auth_token()


async def _json_body(request: Request) -> dict | None:
    """Parse a JSON request body, returning a dict or None. Endpoints turn None
    into a 400 instead of letting malformed JSON / a non-object body raise a 500."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 — malformed body, wrong content-type, etc.
        return None
    return body if isinstance(body, dict) else None


def _strlist(value: Any) -> list[str]:
    """Coerce an arbitrary JSON value into a list of non-empty strings.
    Tolerates a bare string, None, numbers, or junk so endpoints never 500 on
    e.g. ``tags: "abc"`` or ``tags: [1]``."""
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    return [s for s in (str(v).strip() for v in value) if s]


# --- Read endpoints -------------------------------------------------------

async def _index(_request: Request) -> HTMLResponse:
    # no-store so an edited dashboard always reloads fresh (the HTML is baked into
    # this module; without this the browser serves a stale page while the API
    # keeps returning live data — confusing "old icons, new counts" symptom).
    return HTMLResponse(INDEX_HTML, headers={"Cache-Control": "no-store"})


# These reads hit the Things SQLite DB (hundreds of ms — _sidebar scans ~1.3k
# projects). Run them off the event loop so they can't stall concurrent requests
# — most importantly the quick-add resolve poll, whose asyncio.sleep clock would
# otherwise stretch from ~1.8s to many seconds, making "Add" look dead.
async def _state(_request: Request) -> JSONResponse:
    try:
        return JSONResponse({"ok": True, "board": await run_in_threadpool(reads.board)})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc), "board": {}})


async def _sidebar(_request: Request) -> JSONResponse:
    try:
        sidebar = await run_in_threadpool(reads.sidebar)
        return JSONResponse({"ok": True, "auth": bool(_auth_token()), "sidebar": sidebar})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc), "sidebar": {}})


async def _items(request: Request) -> JSONResponse:
    list_id = request.query_params.get("id", "today")
    try:
        # An area folds in its projects' tasks unless the user turned roll-up off
        # for that area (per-area browser pref). Ignored for non-area lists.
        rollup = boardcfg.area_rollup(list_id)
        data = await run_in_threadpool(lambda: reads.list_items(list_id, rollup=rollup))
        return JSONResponse({"ok": True, **data})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc), "items": []})


async def _item(request: Request) -> JSONResponse:
    detail = await run_in_threadpool(reads.item_detail, request.query_params.get("id", ""))
    return JSONResponse({"ok": detail is not None, "item": detail})


async def _search(request: Request) -> JSONResponse:
    q = (request.query_params.get("q") or "").strip()
    if len(q) < 2:
        return JSONResponse({"ok": True, "items": []})
    try:
        # Go through reads.search (not things.search directly) so the THINGS_DB
        # override is honored and the SQLite read runs off the event loop.
        res = await run_in_threadpool(reads.search, q)
        items = [reads._card(t) for t in (res or []) if t.get("type") == "to-do"][:60]
        return JSONResponse({"ok": True, "items": items})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc), "items": []})


# --- Boards + config ------------------------------------------------------

async def _board(request: Request) -> JSONResponse:
    board = boardcfg.get_board(request.query_params.get("id", ""))
    if board is None:
        return JSONResponse({"ok": False, "error": "board not found", "columns": []})
    try:
        cards = await run_in_threadpool(reads.board_cards, board)
        link_table = boardcfg.links()
        for card in cards:
            card["repos"] = link_table.get(card["id"], {}).get("repos", [])
        placements = board.get("placements") or {}
        columns = board.get("columns") or []
        buckets: dict[str, list] = {c: [] for c in columns}
        unsorted: list = []
        for card in cards:
            col = placements.get(card["id"])
            (buckets[col] if col in buckets else unsorted).append(card)
        out = []
        if unsorted:
            out.append({"name": None, "title": "Unsorted", "cards": unsorted})
        for c in columns:
            out.append({"name": c, "title": c, "cards": buckets[c]})
        return JSONResponse(
            {"ok": True, "auth": bool(_auth_token()), "board": board, "columns": out}
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc), "columns": []})


async def _config_get(_request: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "config": boardcfg.load()})


async def _config_post(request: Request) -> JSONResponse:
    # Section merge: only the keys present in the body are overwritten; others are
    # read fresh and preserved (so saving boards can't wipe links, and vice versa).
    try:
        return JSONResponse({"ok": True, "config": boardcfg.merge(await request.json())})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc)})


def _detect_github(repo_path: str) -> str | None:
    """Read owner/repo from a repo's `origin` remote (https or ssh). Best-effort."""
    try:
        r = subprocess.run(
            ["git", "-C", repo_path, "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            return boardcfg._normalize_github(r.stdout.strip())
    except Exception:  # noqa: BLE001
        pass
    return None


async def _link_post(request: Request) -> JSONResponse:
    """Set one item's repo list, without touching anything else in the config.

    Auto-detects each repo's GitHub from its `origin` remote when not provided.
    """
    try:
        body = await request.json()
        item_id = str(body.get("item_id") or "")
        if not item_id:
            return JSONResponse({"ok": False, "error": "missing item_id"})
        repos = body.get("repos") or []
        for r in repos:
            if isinstance(r, dict) and r.get("repo") and not r.get("github"):
                path = boardcfg._normalize_repo(r["repo"])
                if path and os.path.isdir(path):
                    r["github"] = await run_in_threadpool(_detect_github, path)
        cfg = boardcfg.set_item_repos(item_id, body.get("kind", "project"), repos)
        return JSONResponse({"ok": True, "config": cfg})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc)})


# --- Writes (task editing requires THINGS_AUTH_TOKEN) ----------------------

async def _update(request: Request) -> JSONResponse:
    token = _auth_token()
    if not token:
        return JSONResponse({"ok": False, "error": "THINGS_AUTH_TOKEN not set"})
    body = await _json_body(request)
    if body is None:
        return JSONResponse({"ok": False, "error": "invalid JSON body"}, status_code=400)
    if not body.get("id"):
        return JSONResponse({"ok": False, "error": "missing id"})
    params: dict[str, Any] = {"id": str(body["id"])}
    for key in ("title", "notes", "when", "deadline"):
        if body.get(key) is not None:
            params[key] = str(body[key])
    if body.get("tags") is not None:
        params["tags"] = ",".join(_strlist(body["tags"]))
    if body.get("append_notes"):
        params["append-notes"] = str(body["append_notes"])
    if body.get("add_tags"):
        params["add-tags"] = ",".join(_strlist(body["add_tags"]))
    if body.get("completed"):
        params["completed"] = True
    if body.get("canceled"):
        params["canceled"] = True
    if body.get("list_id"):
        params["list-id"] = body["list_id"]   # move a to-do to a project/area (⌘K "Move to project")
    if body.get("heading") is not None:
        params["heading"] = body["heading"]   # move a to-do under a heading within its project (drag onto a heading)
    try:
        await run_in_threadpool(lambda: execute("update", params, auth_token=token))
        return JSONResponse({"ok": True})
    except ThingsURLError as exc:
        return JSONResponse({"ok": False, "error": str(exc)})


async def _pulse(request: Request) -> JSONResponse:
    """Best-effort git/GitHub pulse for a linked item's repos (board cards): commits in
    the last 7 days, time since last commit, open PR count. Missing repo dirs / no `gh`
    just yield fewer fields — never an error."""
    item = boardcfg.links().get(str(request.query_params.get("item_id", "")))
    if not item:
        return JSONResponse({"ok": False, "repos": []})
    # The git/gh shell-outs (up to ~8s each, several repos) would block the single
    # event loop and freeze every other dashboard request — run them off-thread.
    out = await run_in_threadpool(_pulse_repos, item)
    return JSONResponse({"ok": True, "repos": out})


def _pulse_repos(item: dict) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in item.get("repos", []):
        gh = entry.get("github") or ""
        info: dict[str, Any] = {"label": entry.get("label") or (gh.split("/")[-1] if gh else "repo")}
        repo = entry.get("repo")
        if repo and os.path.isdir(repo):
            try:
                r = subprocess.run(["git", "-C", repo, "log", "-1", "--format=%cr"],
                                   capture_output=True, text=True, timeout=5)
                if r.returncode == 0 and r.stdout.strip():
                    info["last_commit"] = r.stdout.strip()
                r2 = subprocess.run(["git", "-C", repo, "rev-list", "--count", "--since=7 days ago", "HEAD"],
                                    capture_output=True, text=True, timeout=5)
                if r2.returncode == 0 and r2.stdout.strip().isdigit():
                    info["commits_7d"] = int(r2.stdout.strip())
            except Exception:  # noqa: BLE001
                pass
        if gh and _GITHUB_SLUG_RE.match(gh) and shutil.which("gh"):
            try:
                r3 = subprocess.run(["gh", "pr", "list", "-R", gh, "--state", "open", "--json", "number"],
                                    capture_output=True, text=True, timeout=8)
                if r3.returncode == 0:
                    info["open_prs"] = len(json.loads(r3.stdout or "[]"))
            except Exception:  # noqa: BLE001
                pass
        out.append(info)
    return out


async def _add(request: Request) -> JSONResponse:
    """Quick-add a to-do or project from the dashboard. Create-only → no token needed.
    (Areas can't be created — the URL Scheme has no add-area command.)"""
    body = await _json_body(request)
    if body is None:
        return JSONResponse({"ok": False, "error": "invalid JSON body"}, status_code=400)
    kind = body.get("kind", "todo")
    title = (body.get("title") or "").strip()
    if not title:
        return JSONResponse({"ok": False, "error": "missing title"})
    try:
        notes = (body.get("notes") or "").strip()
        # When the client staged an image, it needs the new item's UUID to attach it.
        # The URL Scheme doesn't return it, so snapshot matching titles, create, then
        # poll for the one that's new. Skipped unless `resolve` is set (avoids the poll).
        resolve = bool(body.get("resolve"))
        # find_by_exact_title is an exact-match single-column read (~3ms) — run it
        # INLINE, not via run_in_threadpool. Through the threadpool it would queue
        # behind the page's in-flight reads/pulse (git/gh can hold threads for
        # seconds), stretching the resolve poll below to ~5s and making "Add" look
        # dead. 3ms on the loop is far cheaper than waiting for a free thread.
        before = {t["uuid"] for t in reads.find_by_exact_title(title)} if resolve else set()
        if kind == "project":
            params: dict[str, Any] = {"title": title}
            if notes:
                params["notes"] = notes
            if body.get("area_id"):
                params["area-id"] = body["area_id"]
            await run_in_threadpool(lambda: execute("add-project", params))
        else:
            params = {"title": title}
            if notes:
                params["notes"] = notes
            if body.get("when"):
                params["when"] = body["when"]
            if body.get("deadline"):
                params["deadline"] = body["deadline"]
            if _strlist(body.get("tags")):
                params["tags"] = ",".join(_strlist(body.get("tags")))
            if body.get("list_id"):
                params["list-id"] = body["list_id"]
            await run_in_threadpool(lambda: execute("add", params))
        new_uuid = None
        if resolve:
            for _ in range(12):  # Things writes the DB asynchronously after the URL fires
                await asyncio.sleep(0.15)
                matches = reads.find_by_exact_title(title)   # inline (~3ms); never threadpool-starved
                cands = [t for t in matches if t["uuid"] not in before]
                if cands:
                    new_uuid = max(cands, key=lambda t: t.get("created") or 0)["uuid"]
                    break
        return JSONResponse({"ok": True, "uuid": new_uuid})
    except ThingsURLError as exc:
        return JSONResponse({"ok": False, "error": str(exc)})


async def _rename(request: Request) -> JSONResponse:
    """Rename a project inline from the dashboard header. (Board renames are client-side
    config; areas can't be renamed — the Things URL Scheme has no area-update command.)"""
    body = await _json_body(request)
    if body is None:
        return JSONResponse({"ok": False, "error": "invalid JSON body"}, status_code=400)
    item_id = str(body.get("id") or "")
    title = (body.get("title") or "").strip()
    kind = body.get("kind")
    if not item_id or not title:
        return JSONResponse({"ok": False, "error": "missing id/title"})
    if kind == "area":
        return JSONResponse({"ok": False, "error": "Things' URL Scheme can't rename areas — rename it in the Things app."})
    if kind != "project":
        return JSONResponse({"ok": False, "error": "bad kind"})
    if not _auth_token():
        return JSONResponse({"ok": False, "error": "THINGS_AUTH_TOKEN not set"})
    try:
        await run_in_threadpool(lambda: execute("update-project", {"id": item_id, "title": title}, auth_token=_auth_token()))
        return JSONResponse({"ok": True})
    except ThingsURLError as exc:
        return JSONResponse({"ok": False, "error": str(exc)})


async def _open(request: Request) -> JSONResponse:
    """Open a linked repo in the editor or its GitHub page.

    Takes only an item_id + repo index + target; the path/url is looked up and
    validated server-side (never trusted from the request).
    """
    body = await _json_body(request)
    if body is None:
        return JSONResponse({"ok": False, "error": "invalid JSON body"}, status_code=400)
    item = boardcfg.links().get(str(body.get("item_id")))
    if not item:
        return JSONResponse({"ok": False, "error": "not linked"})
    repos = item.get("repos", [])
    idx = body.get("repo_index", 0)
    if not isinstance(idx, int) or idx < 0 or idx >= len(repos):
        return JSONResponse({"ok": False, "error": "bad repo index"})
    entry = repos[idx]
    target = body.get("target")
    prefs = boardcfg.prefs()
    if target == "github":
        gh = entry.get("github")
        if not gh or not _GITHUB_SLUG_RE.match(gh):
            return JSONResponse({"ok": False, "error": "no valid github for this repo"})
        await run_in_threadpool(lambda: subprocess.run(["open", f"https://github.com/{gh}"], check=False, timeout=5))
        return JSONResponse({"ok": True})
    path = entry.get("repo")
    if not path or not os.path.isdir(path):
        return JSONResponse({"ok": False, "error": "repo path not found on disk"})
    if target == "editor":
        editor = prefs.get("editor") or os.environ.get("SUUR_THINGS_EDITOR")
        cmd = [editor, path] if editor and shutil.which(editor) else ["open", path]
        await run_in_threadpool(lambda: subprocess.run(cmd, check=False, timeout=5))
        return JSONResponse({"ok": True})
    if target == "terminal":
        app = prefs.get("terminal") or os.environ.get("SUUR_THINGS_TERMINAL") or "Terminal"
        await run_in_threadpool(lambda: subprocess.run(["open", "-a", app, path], check=False, timeout=5))
        return JSONResponse({"ok": True})
    return JSONResponse({"ok": False, "error": "bad target"})


_MAX_ATTACH_BYTES = 12 * 1024 * 1024  # 12 MB per image


async def _attach(request: Request) -> JSONResponse:
    """Attach an image to a task. Image bytes are sent as base64 (or a data: URL);
    they're written to disk and recorded in the browser-side overlay (no Things
    token needed to store). If a token IS set, a file:// reference is appended to
    the task's notes so the Things app shows it too."""
    body = await _json_body(request)
    if body is None:
        return JSONResponse({"ok": False, "error": "invalid JSON body"}, status_code=400)
    item_uuid = str(body.get("uuid") or "").strip()
    if not item_uuid:
        return JSONResponse({"ok": False, "error": "missing uuid"})
    raw = body.get("data") or ""
    mime = (body.get("mime") or "").strip().lower()
    if isinstance(raw, str) and raw.startswith("data:"):  # data:image/png;base64,XXXX
        head, _, b64 = raw.partition(",")
        if not mime and ";" in head:
            mime = head[5:head.index(";")].strip().lower()
        raw = b64
    try:
        data = base64.b64decode(raw, validate=True)
    except (ValueError, TypeError):
        return JSONResponse({"ok": False, "error": "invalid base64 image data"})
    if not data:
        return JSONResponse({"ok": False, "error": "empty image"})
    if len(data) > _MAX_ATTACH_BYTES:
        return JSONResponse({"ok": False, "error": f"image too large (max {_MAX_ATTACH_BYTES // (1024*1024)}MB)"})
    try:
        meta = boardcfg.save_attachment(item_uuid, data, mime,
                                        body.get("name") or "image", body.get("caption"))
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)})

    note_updated = False
    token = _auth_token()
    if token:
        try:
            path = str(boardcfg.attachment_path(item_uuid, meta))
            existing = (await run_in_threadpool(reads.get, item_uuid) or {}).get("notes") or ""
            if boardcfg.note_ref_url(path) not in existing:  # don't duplicate on re-attach
                await run_in_threadpool(lambda: execute(
                    "update", {"id": item_uuid, "append-notes": boardcfg.note_ref_line(meta["name"], path)},
                    auth_token=token))
            note_updated = True
        except ThingsURLError:
            pass  # storing succeeded; the note reference is best-effort
    return JSONResponse({"ok": True, "attachment": meta, "note_updated": note_updated})


async def _attachment(request: Request) -> FileResponse | JSONResponse:
    """Serve an attachment's bytes. Only files recorded in the overlay are served,
    and the path is rebuilt server-side from the stored metadata — the request never
    supplies a path, so this can't be turned into an arbitrary-file read."""
    item_uuid = str(request.query_params.get("uuid") or "")
    att_id = str(request.query_params.get("id") or "")
    meta = boardcfg.attachment_meta(item_uuid, att_id)  # None unless both are known + valid
    if not meta:
        return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
    path = boardcfg.attachment_path(item_uuid, meta)
    base = boardcfg._attach_dir().resolve()
    try:
        rp = path.resolve()
        rp.relative_to(base)  # defense in depth: must stay under the attachments dir
    except (ValueError, OSError):
        return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
    if not rp.is_file():
        return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
    return FileResponse(rp, media_type=meta["mime"], headers={"Cache-Control": "private, max-age=3600"})


async def _detach(request: Request) -> JSONResponse:
    body = await _json_body(request)
    if body is None:
        return JSONResponse({"ok": False, "error": "invalid JSON body"}, status_code=400)
    removed = boardcfg.remove_attachment(str(body.get("uuid") or ""), str(body.get("id") or ""))
    return JSONResponse({"ok": removed})


def _evict_jobs() -> None:
    now = time.time()
    for jid in [k for k, v in _ORGANIZE_JOBS.items()
                if v.get("status") != "running" and now - v.get("ts", now) > _ORGANIZE_TTL]:
        _ORGANIZE_JOBS.pop(jid, None)


async def _organize_post(request: Request) -> JSONResponse:
    """Start a background 'organize folder' agent run. Returns a job_id to poll."""
    if not _auth_token():
        return JSONResponse({"ok": False, "error": "THINGS_AUTH_TOKEN not set (needed to apply changes)"})
    body = await _json_body(request)
    if body is None:
        return JSONResponse({"ok": False, "error": "invalid JSON body"}, status_code=400)
    folder_id = str(body.get("folder_id") or "")
    workflow = str(body.get("workflow") or "organize")   # organize | triage | calm
    if not folder_id:
        return JSONResponse({"ok": False, "error": "missing folder_id"})
    agent = organizer.pick_agent(boardcfg.prefs())
    if not agent:
        return JSONResponse({"ok": False, "error": "no agent CLI found — install Claude Code or Codex"})

    # Reserve the single job slot atomically: dedupe + global-cap + insert under
    # one lock, so two concurrent POSTs can't both pass the cap and spawn jobs.
    # The slow I/O below runs OUTSIDE the lock; on failure we release the slot.
    job_id = _uuid.uuid4().hex[:8]
    with _ORGANIZE_LOCK:
        _evict_jobs()
        for jid, job in _ORGANIZE_JOBS.items():  # dedupe: same folder+workflow already running
            if job.get("status") == "running" and job.get("folder_id") == folder_id and job.get("workflow") == workflow:
                return JSONResponse({"ok": True, "job_id": jid})
        if any(j.get("status") == "running" for j in _ORGANIZE_JOBS.values()):  # global cap of 1
            return JSONResponse({"ok": False, "error": "another organize job is already running"})
        _ORGANIZE_JOBS[job_id] = {"status": "running", "folder_id": folder_id, "workflow": workflow,
                                  "ts": time.time(), "suggestions": None, "error": None, "count": 0}

    try:
        cards = reads.list_items(folder_id).get("items", [])[: organizer.MAX_TASKS]
        tasks = []
        for c in cards:
            full = reads.get(c["uuid"]) or {}
            tasks.append({"uuid": c["uuid"], "title": c.get("title"),
                          "notes": full.get("notes"), "tags": full.get("tags") or c.get("tags")})
        if not tasks:
            _ORGANIZE_JOBS.pop(job_id, None)  # release the reserved slot
            return JSONResponse({"ok": False, "error": "no open tasks in this folder"})
        obj = reads.get(folder_id)
        title = (obj.get("title") if obj else None) or folder_id
        existing_tags = [t.get("title") for t in reads.tags() if t.get("title")]
        dest_names: list[str] = []
        if workflow == "triage":   # give the agent valid filing destinations (resolved to ids client-side)
            dest_names = [p["title"] for p in reads.projects()
                          if p.get("status") == "incomplete" and p.get("title")] \
                         + [a["title"] for a in reads.areas() if a.get("title")]
    except Exception as exc:  # noqa: BLE001
        _ORGANIZE_JOBS.pop(job_id, None)  # release the reserved slot
        return JSONResponse({"ok": False, "error": str(exc)})

    model = boardcfg.prefs().get("agent_model") or organizer.DEFAULT_MODEL
    titles = {t["uuid"]: t.get("title") for t in tasks}   # so the review modal can name each task
    _ORGANIZE_JOBS[job_id]["count"] = len(tasks)

    def _work() -> None:
        try:
            sug = organizer.organize(title, tasks, existing_tags, agent, model,
                                     workflow=workflow, projects=dest_names)
            for s in sug:
                s["title"] = titles.get(s["uuid"])
            _ORGANIZE_JOBS[job_id].update(status="done", suggestions=sug, ts=time.time())
        except Exception as exc:  # noqa: BLE001
            _ORGANIZE_JOBS[job_id].update(status="error", error=str(exc), ts=time.time())

    threading.Thread(target=_work, daemon=True, name=f"organize-{job_id}").start()
    return JSONResponse({"ok": True, "job_id": job_id, "count": len(tasks), "agent": agent})


async def _organize_get(request: Request) -> JSONResponse:
    job = _ORGANIZE_JOBS.get(request.query_params.get("job_id", ""))
    if not job:
        return JSONResponse({"ok": True, "status": "unknown"})  # server restarted / evicted
    return JSONResponse({"ok": True, "status": job["status"],
                         "suggestions": job.get("suggestions"), "error": job.get("error")})


def _allowed_origins(port: int) -> set[str]:
    """The dashboard's own origins. The browser is opened at 127.0.0.1; a user may
    also type localhost. Both resolve to the IPv4 bind, so both are legitimate."""
    return {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}


def create_app(port: int = DEFAULT_PORT) -> Starlette:
    return Starlette(
        routes=[
            Route("/", _index),
            Route("/api/organize", _organize_get),
            Route("/api/organize", _organize_post, methods=["POST"]),
            Route("/api/state", _state),
            Route("/api/sidebar", _sidebar),
            Route("/api/items", _items),
            Route("/api/item", _item),
            Route("/api/search", _search),
            Route("/api/pulse", _pulse),
            Route("/api/board", _board),
            Route("/api/config", _config_get),
            Route("/api/config", _config_post, methods=["POST"]),
            Route("/api/link", _link_post, methods=["POST"]),
            Route("/api/update", _update, methods=["POST"]),
            Route("/api/rename", _rename, methods=["POST"]),
            Route("/api/add", _add, methods=["POST"]),
            Route("/api/open", _open, methods=["POST"]),
            Route("/api/attachment", _attachment),
            Route("/api/attach", _attach, methods=["POST"]),
            Route("/api/detach", _detach, methods=["POST"]),
        ],
        middleware=[
            # TrustedHost first (outermost): reject foreign Host headers before any
            # handler runs — closes DNS-rebinding for the read endpoints too.
            Middleware(TrustedHostMiddleware, allowed_hosts=list(_ALLOWED_HOSTS), www_redirect=False),
            Middleware(_OriginGuard, allowed_origins=_allowed_origins(port)),
        ],
    )


# --- Server lifecycle -----------------------------------------------------

# Chromium "app mode" (`--app=URL`) gives the dashboard its own frameless window
# (no tabs, no address bar) and a Dock icon while open — the closest thing to a
# native app with zero extra deps. Try the installed Chromium browsers in order;
# if none are present, or app mode fails, fall back to a normal browser tab.
_APP_BROWSERS = ("Google Chrome", "Brave Browser", "Microsoft Edge", "Chromium", "Vivaldi", "Arc")


def _open_url(url: str, app_mode: bool = False) -> None:
    if app_mode:
        for app in _APP_BROWSERS:
            if os.path.isdir(f"/Applications/{app}.app"):
                try:
                    subprocess.run(["open", "-na", app, "--args", f"--app={url}"],
                                   check=True, timeout=5)
                    return
                except Exception:  # noqa: BLE001
                    break  # an app exists but launch failed — fall back to a normal open
    try:
        subprocess.run(["open", url], check=False, timeout=5)
    except Exception:  # noqa: BLE001
        pass


def _dashboard_alive(port: int) -> bool:
    """True if *our* dashboard already answers on this port, so we reuse it instead
    of spawning a duplicate on a random port."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=0.6) as r:
            return b"SUUR Things" in r.read(4000)
    except Exception:  # noqa: BLE001
        return False


def _pick_port(preferred: int = DEFAULT_PORT) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # SO_REUSEADDR so a quick restart can rebind `preferred` while the old
        # socket is in TIME_WAIT (uvicorn sets it too). Without this the precheck
        # fails on rapid restarts and the dashboard silently hops to a random port.
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def ensure_running(open_browser: bool = True, app_mode: bool = False) -> str:
    if _running.get("url"):
        if open_browser:
            _open_url(_running["url"], app_mode)
        return _running["url"]
    if _dashboard_alive(DEFAULT_PORT):  # reuse an instance already on the stable port
        url = f"http://127.0.0.1:{DEFAULT_PORT}"
        _running.update(url=url, port=DEFAULT_PORT)
        if open_browser:
            _open_url(url, app_mode)
        return url
    port = _pick_port()
    config = uvicorn.Config(create_app(port), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True, name="things-dashboard")
    thread.start()
    url = f"http://127.0.0.1:{port}"
    _running.update(url=url, port=port, thread=thread, server=server)
    # Wait until the server is actually accepting connections before opening the
    # browser — otherwise the tab can load before uvicorn binds and show a refused
    # connection. Poll the port for up to ~3s.
    deadline = time.time() + 3.0
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)
    if open_browser:
        _open_url(url, app_mode)
    return url


def serve_foreground(port: int = DEFAULT_PORT, open_browser: bool = True, app_mode: bool = False) -> None:
    if _dashboard_alive(port):  # already running on the stable port — don't duplicate
        url = f"http://127.0.0.1:{port}"
        print(f"Things dashboard already running → {url}")
        if open_browser:
            _open_url(url, app_mode)
        return
    chosen = _pick_port(port)
    if chosen != port:
        print(f"Port {port} is busy (not our dashboard); using {chosen} instead.")
    url = f"http://127.0.0.1:{chosen}"
    print(f"Things dashboard → {url}  ({'app window' if app_mode else 'browser'}; Ctrl-C to stop)")
    if open_browser:
        _open_url(url, app_mode)
    uvicorn.run(create_app(chosen), host="127.0.0.1", port=chosen, log_level="warning")


# --- Frontend (self-contained, no external deps) --------------------------

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SUUR Things</title>\n<link rel="icon" type="image/png" href="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAAAAXNSR0IArs4c6QAAAJhlWElmTU0AKgAAAAgABAEaAAUAAAABAAAAPgEbAAUAAAABAAAARgEoAAMAAAABAAIAAIdpAAQAAAABAAAATgAAAAAAAABIAAAAAQAAAEgAAAABAASQBAACAAAAFAAAAISgAQADAAAAAQABAACgAgAEAAAAAQAAACCgAwAEAAAAAQAAACAAAAAAMjAyNjowNToyNSAxMjoyNTozNAC2nQgPAAAACXBIWXMAAAsTAAALEwEAmpwYAAABzWlUWHRYTUw6Y29tLmFkb2JlLnhtcAAAAAAAPHg6eG1wbWV0YSB4bWxuczp4PSJhZG9iZTpuczptZXRhLyIgeDp4bXB0az0iWE1QIENvcmUgNi4wLjAiPgogICA8cmRmOlJERiB4bWxuczpyZGY9Imh0dHA6Ly93d3cudzMub3JnLzE5OTkvMDIvMjItcmRmLXN5bnRheC1ucyMiPgogICAgICA8cmRmOkRlc2NyaXB0aW9uIHJkZjphYm91dD0iIgogICAgICAgICAgICB4bWxuczp4bXA9Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC8iPgogICAgICAgICA8eG1wOkNyZWF0b3JUb29sPkFkb2JlIFBob3Rvc2hvcCAyNy44ICgyMDI2MDUxNi5tLjM1NDMgYzJmYzU1NikgIChNYWNpbnRvc2gpPC94bXA6Q3JlYXRvclRvb2w+CiAgICAgICAgIDx4bXA6Q3JlYXRlRGF0ZT4yMDI2LTA1LTI1VDEyOjI1OjM0PC94bXA6Q3JlYXRlRGF0ZT4KICAgICAgPC9yZGY6RGVzY3JpcHRpb24+CiAgIDwvcmRmOlJERj4KPC94OnhtcG1ldGE+CkLx6vgAAAZWSURBVEgNjVZrbFRFFJ65j91tC20plEYQIpjwSKloQqgIRn4YHlYTg0FjJCCCUCxpUsBgYohGo/GNMTExhhAUiGj0jxoSNPxQQZ5FISCIWNJS2tKWR1+73bt37vh9M7ulEh497d47c+ac7zxn5spHGtalVFpI4UgpheAvRxhGWufFE/+e+bvpTIObiElXaqxqoVLB1OkVYyaM70n1udIwwRUSIHhprTGAINQ9LbSKFLXAsn+OfRlrUIBh15PxGP9drFFBhlp4MpJaSU1E+sQ3pYGCkdYx6UVSwQDtaBFFArLacQgvXSBBjh45MdeJezIv5uTFYUBH8D8SSjm+68U8J3SgTANgK4VVjB0tXO34vosVj4tShyIinpSe70aZsK+tS6UDKmnR7bjdrZ0yUNoJhevQt1CJTHSlqU2mwnQYRAbCT8TyS4qk7wZBEGotHY98KTymBVNgSxmL+VcbLzUdPBVc7BBpJZA5uqdF3BMFMabBZI+AkW6pb2wJlMkH+ELkufFxZfdUlheOG51KpzOR8pVK+DGPahSQvu/3Nnee23N4+DWnZsaq2ZNmek52lfbhO5PGeCHPpCqTWngpZUZl9v1zaMuxXWe7D5dXzfFLCzOZTBixuIQwStKJROPxswU98pulny+onEcuiGhDoqdmPzlvytzFX69uOdUw9dGZ3aGCE5GOPLxAiL2/L5W8fGXZtCcWzJyHPLLadHlIRIgoWlg5f9Hxx3a0/+SgfLZ3AMxRhGCjMBOKMHpg7DR4jSayBliZIRClHeRQ3D+mnMbQEGg/4x/b1NhgNdmfkiaHmBqCGoKLpkJIhGsbwYTEhkUXs5k41xDKZt6q3f4J9LZLl7bv/Kq5+SKDtNKmAwAHkygx9oUHXCyCzz2OTWQjuj02PHOcrq6uTa+9uf/Awb5ksvrFFVk9GgASNxy2G/xGkWEswjYzoWT9uD0+3A3D8L0PP/7z+Im7x46d+/AcyFsDBCESQbG9wGcNlCmz2ZBZP+5oYNuXO/b8vBetUFtTPWXKZOOhUTKlpD1DeDlYM2O8jYlBOULqkApLAyYx/eW3fVu/2KFCVbVw/uNVC6mYi8B0ByvJIHDAmRpwaAMbQMEA6MlkavMnn+IIq6utKSwsBBDQmy5cePf9zalkauLEe9bWVF9HtsrIivUXxxGH2MkmK2BSYFAXoY/b2zu+/2F3Oki3t7e/9cbrxcVF/f39b7/zQUtra8z3N9TVlowYYd234HxezzH7BbC21Fl8sAaqDM3x48ctX7YEid5/4NDGVzddvnxly9ZtBw4dRkzPPrN41oOVN6LnLAAZySGhi8A0ReCDIV13gQVYs3oljo2t27YfOVK/YvVLHZ2dkK+YVr5q5fKcU0S9gbCEXcD7yNwHuIYYGn1HigZCMMkEr3btmnQ6vX3nrqYLzZjmJRIbN9QVFBTczH14TjXjMZw1Nxis8TpjzU0GB0VABhaFWF9X+/TiRclksrenF0mbfl/FTdEhaSCoNUAoMrJl/Gd+TCxZuWwsEMXZ98rL68pGl+KQf37pEnAM1q0e2f6BGGsAWSBhQrz/KdoVosADz/NWrXyBIobIvRVhO8EDpMcMUGRq8GEOIo5BBB9UjaHgWi0oDuCYvOArgTuYsfieiLkN7Y04OmjkDnmgGwNEHyGvxHmo+y6IiIYcM8DZqhL5+YnSkm9P/HjsZL3neo5jLx1cbLl/e2hgCrJPO5AUhcrRk0e/O727+K7Rju8pFZrUmH0gYSTSgQonlE8+3bxvyZbq9XPXTL+3wvd8HJx0zRDHpmCYkWcPYLMUhpk/zp346NfPWkd0PzR11tVUT4Qr2WxiOan+uVSQQnvAjbLiUZm2nr9+Pxo1Xs3PJFxcTwTLoaIqWVuD9qOpFC6WpJ9yJ4ycMWe2LM0/33kREcS9WFHecFm2t4pZcgQMeK47qqhkmI73dnb19yUBbhsM78Hg1iaXjATPfSnyhw0rLh3ZpZMt1zpUGOKjxnW9/ERClu5ZwP4BANxl2vmBlBfPYxnM/Qxv+W3GWJiVXDic2omxpIMwTPWn0pkgW9sQyxpfU54tN8VDIc0GDYIo6EuTQwiDbOEti8GAzIMDrplf9sGvCdP2XMQG0iGvCw6hEjkIDXNqs4ZshJwJTsi12cKTZL4qjM9Wh5l0+IlNMwry0X9fbQClXNfsrAAAAABJRU5ErkJggg==">
<style>
  :root {
    --side-bg:#f3f4f6; --main-bg:#ffffff; --text:#1d1d20; --muted:#8a8f98;
    --divider:#e8e9eb; --row-hover:#e9ebee; --row-sel:#dfe1e6; --accent:#3478f6;
    --pill-border:#d3d6da; --ring-bg:#d7dade; --ring-fg:#9aa0a8; --badge:#e7e8eb;
    --red:#e0402b; --check-border:#c2c6cc; --header-rule:#ececee; --col-bg:#f0f1f3;
    --card-bg:#ffffff; --card-shadow:0 1px 2px rgba(0,0,0,.07); --overlay:rgba(0,0,0,.28);
    --chip-bg:#e6e8eb; --chip-fg:#41454c; --chip-active-bg:#4a4f57; --chip-active-fg:#fff; --gold:#f5c026;
  }
  html[data-theme="dark"] {
    --side-bg:#23272c; --main-bg:#1b1e23; --text:#e7e9ec; --muted:#888e97;
    --divider:#31363c; --row-hover:#2b3035; --row-sel:#384049; --accent:#4c8dff;
    --pill-border:#474d55; --ring-bg:#3a3f46; --ring-fg:#888e97; --badge:#363b42;
    --red:#ff6453; --check-border:#5a6068; --header-rule:#2e333a; --col-bg:#22262b;
    --card-bg:#2b3036; --card-shadow:0 1px 2px rgba(0,0,0,.3); --overlay:rgba(0,0,0,.5);
    --chip-bg:#363b42; --chip-fg:#c5c9cf; --chip-active-bg:#dfe1e6; --chip-active-fg:#1b1e23; --gold:#f5c026;
  }
  * { box-sizing:border-box; }
  html, body { height:100%; margin:0; overflow:hidden; }
  body { font:14px/1.45 -apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif;
    background:var(--main-bg); color:var(--text); -webkit-font-smoothing:antialiased; }

  .topbar { height:44px; display:flex; align-items:center; gap:10px; padding:0 16px;
    border-bottom:1px solid var(--divider); background:var(--main-bg); }
  .brand { font-weight:800; font-size:13px; letter-spacing:.13em; }
  .grow { flex:1; }
  .iconbtn { border:1px solid var(--divider); background:var(--main-bg); color:var(--text); width:32px;
    height:32px; border-radius:8px; cursor:pointer; font-size:18px; display:flex; align-items:center; justify-content:center; flex:0 0 32px; }
  .iconbtn:hover { background:var(--row-hover); }
  .views { position:absolute; top:44px; left:0; right:0; bottom:0; display:flex; }

  .sidebar { width:272px; flex:0 0 272px; background:var(--side-bg); border-right:1px solid var(--divider);
    display:flex; flex-direction:column; min-height:0; }
  .side-nav { flex:1; overflow-y:auto; padding:14px 10px 8px; }
  .side-foot { flex:none; border:0; border-top:1px solid var(--divider); background:transparent; color:var(--muted);
    cursor:pointer; text-align:left; font:inherit; font-size:12.5px; padding:10px 16px; display:flex; align-items:center; gap:8px; }
  .side-foot:hover { color:var(--text); background:var(--row-hover); }
  .side-foot.active { color:var(--text); background:var(--row-sel); }
  .side-foot svg { width:15px; height:15px; flex:0 0 15px; }
  .side-sep { height:1px; background:var(--divider); margin:10px 10px; }

  .main-head h1.editable { cursor:text; border-radius:6px; padding:1px 5px; margin-left:-5px; }
  .main-head h1.editable:hover { background:var(--row-hover); }
  .main-head h1.editable:focus { outline:none; background:var(--main-bg); box-shadow:inset 0 0 0 2px var(--accent); }

  .about { max-width:640px; line-height:1.62; padding-bottom:40px; }
  .about h2 { font-size:17px; margin:26px 0 8px; }
  .about p, .about li { color:var(--text); }
  .about .lead { font-size:15px; color:var(--muted); }
  .about a { color:var(--accent); text-decoration:none; } .about a:hover { text-decoration:underline; }
  .about code { background:var(--side-bg); padding:1px 5px; border-radius:5px; font-size:12.5px; }
  .about .muted { color:var(--muted); font-size:12.5px; }
  .nav-item, .project { display:flex; align-items:center; gap:9px; padding:6px 10px; margin:1px 0;
    border-radius:7px; cursor:pointer; white-space:nowrap; user-select:none; }
  .project { padding-left:14px; }
  .nav-item:hover, .project:hover { background:var(--row-hover); }
  .nav-item.active, .project.active, .area-head.active { background:var(--row-sel); }
  .nav-item.drop-when { outline:2px dashed var(--accent); outline-offset:-2px; background:var(--row-hover); }
  .nav-item .ico, .project .ico { width:18px; flex:0 0 18px; font-size:14px; display:flex; align-items:center; justify-content:center; }
  .ico svg { width:18px; height:18px; display:block; }
  .main-head .ico svg { width:25px; height:25px; }
  .main-head .ico svg.ring { width:22px; height:22px; }
  .nav-item .label, .project .label { flex:1; overflow:hidden; text-overflow:ellipsis; }
  .nav-item .count { color:var(--muted); font-size:12.5px; font-variant-numeric:tabular-nums; }
  .nav-sep { height:14px; }
  .group-head { padding:7px 10px 3px; margin-top:10px; font-weight:600; font-size:12px;
    text-transform:uppercase; letter-spacing:.04em; color:var(--muted); display:flex; align-items:center; }
  .group-head .add { margin-left:auto; cursor:pointer; font-size:14px; padding:0 4px; border-radius:5px; }
  .group-head .add:hover { background:var(--row-hover); color:var(--text); }
  .area-head { padding:7px 6px 3px; margin-top:8px; font-weight:600; font-size:13.5px;
    display:flex; align-items:center; gap:4px; white-space:nowrap; cursor:pointer; border-radius:7px; }
  .area-head:hover { background:var(--row-hover); }
  .area-head .chev { width:15px; flex:0 0 15px; text-align:center; color:var(--muted); font-size:9px; cursor:pointer; border-radius:4px; }
  .area-head .chev:hover { background:var(--divider); }
  svg.ring { flex:0 0 16px; }
  .ring-bg { fill:none; stroke:var(--ring-bg); stroke-width:2; }
  .ring-fg { fill:none; stroke:var(--ring-fg); stroke-width:2; stroke-linecap:round; }

  .main { flex:1; min-width:0; display:flex; flex-direction:column; }
  .main-head { display:flex; align-items:center; gap:11px; padding:26px 40px 0; margin-bottom:18px; flex:none; }
  .main-head .ico { font-size:24px; display:flex; align-items:center; } .main-head h1 { font-size:25px; font-weight:700; letter-spacing:-.01em; margin:0; }
  .main-head .grow { flex:1; }
  #content { flex:1; min-height:0; overflow-y:auto; padding:0 40px 80px; }
  .main.fill #content { overflow:hidden; padding:0 18px 18px; }
  .board-wrap { display:flex; gap:14px; align-items:flex-start; height:100%; overflow-x:auto; }

  .grp-head { display:flex; align-items:center; gap:8px; font-weight:600; font-size:14.5px;
    padding:18px 0 7px; border-bottom:1px solid var(--header-rule); margin-bottom:4px; }
  .grp-head.drop { outline:2px dashed var(--accent); outline-offset:3px; border-radius:6px; }
  .heading-dropzone { display:none; color:var(--muted); font-size:12.5px; padding:9px 12px; margin:4px 0 6px; max-width:760px;
    border:1px dashed var(--pill-border); border-radius:8px; text-align:center; }
  body.dragging-task .heading-dropzone { display:block; }       /* only show while dragging a task */
  .heading-dropzone.drop { border-color:var(--accent); color:var(--text); background:var(--row-hover); }
  .row { display:flex; align-items:center; gap:11px; padding:6px 8px; border-radius:7px; cursor:pointer; max-width:760px; }
  .row:hover { background:var(--row-hover); }
  .row.is-done .title { color:var(--muted); }
  .box { width:17px; height:17px; flex:0 0 17px; border:1.5px solid var(--check-border);
    border-radius:5px; display:flex; align-items:center; justify-content:center; }
  .row .box:hover { border-color:var(--accent); }
  .box.done { background:var(--accent); border-color:var(--accent); }
  .box.done::after { content:"✓"; color:#fff; font-size:11px; font-weight:700; }
  .box.cancel { background:var(--muted); border-color:var(--muted); }
  .box.cancel::after { content:"✕"; color:#fff; font-size:10px; font-weight:700; }
  .title { flex:1 1 auto; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .meta { display:flex; align-items:center; gap:6px; flex:0 0 auto; }
  .pill { font-size:11px; padding:2px 8px; border:0; background:var(--chip-bg); color:var(--chip-fg); border-radius:11px; white-space:nowrap; }
  .note-ico { color:var(--muted); font-size:12px; }
  .att-ico { color:var(--muted); display:inline-flex; align-items:center; }
  .att-ico svg { width:13px; height:13px; }
  .due { display:inline-flex; align-items:center; gap:4px; color:var(--red); font-size:12px; white-space:nowrap; }
  .due .dot { width:9px; height:9px; border-radius:50%; background:var(--red); display:inline-block; }
  .empty, .err { color:var(--muted); padding:40px 4px; } .err { color:var(--red); }
  .proj-notes { color:var(--muted); font-size:14px; line-height:1.55; margin:-4px 0 18px; max-width:760px; white-space:pre-wrap; }
  .proj-notes a { color:var(--accent); }
  /* Things-style tag filter chips */
  .filterbar { display:none; gap:7px; padding:0 40px 14px; align-items:center; flex:none; overflow-x:auto; }
  .filterbar.show { display:flex; }
  .filterbar::-webkit-scrollbar { display:none; }
  .chip { font-size:12px; line-height:1; padding:5px 11px; border-radius:13px; background:var(--chip-bg);
    color:var(--chip-fg); cursor:pointer; white-space:nowrap; user-select:none; border:1px solid transparent;
    display:inline-flex; align-items:center; gap:5px; flex:0 0 auto; }
  .chip:hover { filter:brightness(.96); }
  .chip.active { background:var(--chip-active-bg); color:var(--chip-active-fg); font-weight:600; }
  .chip svg { width:12px; height:12px; }

  /* List | Matrix view toggle */
  .viewtog { display:none; background:var(--chip-bg); border-radius:8px; padding:2px; gap:2px; }
  .viewtog.show { display:inline-flex; }
  .vt { border:0; background:transparent; color:var(--chip-fg); font:inherit; font-size:12.5px; padding:4px 12px; border-radius:6px; cursor:pointer; }
  .vt.on { background:var(--main-bg); color:var(--text); box-shadow:0 1px 2px rgba(0,0,0,.08); font-weight:600; }

  /* ⌘K command palette */
  .cmdk-btn { margin-left:20px; display:flex; align-items:center; gap:8px; width:280px; max-width:40vw; font:inherit;
    font-size:13px; padding:6px 11px; border-radius:8px; border:1px solid var(--divider); background:var(--side-bg); color:var(--muted); cursor:pointer; }
  .cmdk-btn:hover { border-color:var(--pill-border); }
  .cmdk-btn svg { width:14px; height:14px; flex:0 0 14px; }
  .cmdk-btn .ck-ph { flex:1; text-align:left; }
  .kbd { font-size:11px; border:1px solid var(--pill-border); border-radius:5px; padding:0 5px; color:var(--muted); }
  .ck-panel { background:var(--main-bg); border-radius:12px; width:560px; max-width:92vw; box-shadow:0 18px 56px rgba(0,0,0,.4); overflow:hidden; }
  #cmdk-input { width:100%; border:0; border-bottom:1px solid var(--divider); background:transparent; color:var(--text); font:15px/1.4 inherit; padding:15px 18px; outline:none; }
  #cmdk-input::placeholder { color:var(--muted); }
  .ck-list { max-height:60vh; overflow-y:auto; padding:6px; }
  .ck-row { display:flex; align-items:center; gap:10px; padding:8px 12px; border-radius:8px; cursor:pointer; }
  .ck-row.sel { background:var(--row-sel); }
  .ck-ico { width:18px; flex:0 0 18px; display:flex; align-items:center; justify-content:center; } .ck-ico svg { width:16px; height:16px; }
  .ck-label { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .ck-hint { color:var(--muted); font-size:11.5px; white-space:nowrap; }

  /* Project cards (area view) */
  .projcards { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:12px; max-width:760px; margin:2px 0 22px; }
  .projcard { background:var(--card-bg); border-radius:10px; padding:13px 14px; box-shadow:var(--card-shadow);
    cursor:pointer; display:flex; align-items:center; gap:10px; }
  .projcard:hover { background:var(--row-hover); }
  .projcard svg.ring { width:18px; height:18px; flex:0 0 18px; }
  .projcard .pt { font-weight:600; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }

  /* Cards view (with YouTube thumbnails) */
  .cardgrid { display:grid; grid-template-columns:repeat(auto-fill,minmax(248px,1fr)); gap:16px; max-width:1120px; }
  .taskcard { background:var(--card-bg); border-radius:12px; box-shadow:var(--card-shadow); cursor:pointer; overflow:hidden; }
  .taskcard:hover { background:var(--row-hover); }
  .taskcard.is-done .tc-title { color:var(--muted); text-decoration:line-through; }
  .taskcard .thumb { position:relative; aspect-ratio:16/9; background:var(--col-bg); display:flex; align-items:center; justify-content:center; font-size:26px; overflow:hidden; }
  .taskcard .thumb img { width:100%; height:100%; object-fit:cover; display:block; }
  .taskcard .thumb .play { position:absolute; color:#fff; font-size:34px; text-shadow:0 1px 7px rgba(0,0,0,.65); }
  .taskcard .tc-body { padding:11px 13px 13px; }
  .taskcard .tc-title { font-weight:600; font-size:13.5px; line-height:1.35; }
  .taskcard .tc-sub { color:var(--muted); font-size:12px; margin-top:3px; }
  .taskcard .tc-tags { margin-top:8px; display:flex; flex-wrap:wrap; gap:5px; }

  /* Timeline (day) view */
  .tl-wrap { display:flex; gap:16px; height:100%; }
  .tl-pool { width:260px; flex:0 0 260px; background:var(--col-bg); border-radius:12px; display:flex; flex-direction:column; }
  .tl-pool.drop { outline:2px dashed var(--accent); outline-offset:-4px; }
  .tl-durbar { padding:8px 12px 10px; font-size:12px; color:var(--muted); display:flex; align-items:center; gap:8px; }
  .tl-durbar .durtog { display:inline-flex; gap:2px; background:var(--chip-bg); border-radius:7px; padding:2px; }
  .tl-cal { flex:1; overflow-y:auto; }
  .tl-grid { position:relative; margin:6px 8px 6px 0; }
  .tl-hour { position:absolute; left:50px; right:4px; border-top:1px solid var(--divider); height:0; }
  .tl-hlabel { position:absolute; left:0; width:42px; text-align:right; color:var(--muted); font-size:11px; margin-top:-7px; }
  .tl-block { position:absolute; left:54px; right:10px; background:var(--card-bg); border-left:3px solid var(--accent);
    border-radius:6px; box-shadow:var(--card-shadow); padding:3px 9px; overflow:hidden; cursor:grab; }
  .tl-block.dragging { opacity:.4; }
  .tl-block .bt { font-weight:600; font-size:12.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .tl-block .bsub { color:var(--muted); font-size:11px; }

  /* Things-style edit card */
  .editcard { background:var(--main-bg); border-radius:12px; width:460px; max-width:100%; max-height:84vh;
    overflow-y:auto; box-shadow:0 18px 56px rgba(0,0,0,.4); padding:16px 18px 12px; position:relative; }
  .ec-x { position:absolute; top:11px; right:13px; color:var(--muted); cursor:pointer; font-size:14px; line-height:1; }
  .ec-x:hover { color:var(--text); }
  .ec-top { display:flex; align-items:flex-start; gap:11px; padding-right:18px; }
  .ec-box { width:19px; height:19px; flex:0 0 19px; margin-top:3px; border:1.5px solid var(--check-border);
    border-radius:5px; cursor:pointer; display:flex; align-items:center; justify-content:center; }
  .ec-box:hover { border-color:var(--accent); }
  .ec-title { flex:1; font:600 17px/1.3 inherit; color:var(--text); border:0; background:transparent; outline:none;
    padding:0; resize:none; overflow:hidden; }
  .ec-notes { width:100%; border:0; background:transparent; outline:none; color:var(--text); font:14px/1.5 inherit;
    padding:0; margin:8px 0 4px; min-height:22px; resize:none; overflow:hidden; }
  .ec-notes::placeholder, .ec-title::placeholder { color:var(--muted); }
  .ec-pills { display:flex; flex-wrap:wrap; gap:7px; margin:9px 0 2px; }
  .ec-attach { display:flex; flex-wrap:wrap; gap:8px; margin:6px 0 2px; }
  .ec-attach:empty { display:none; }
  .att { position:relative; width:88px; }
  .att img { width:88px; height:88px; object-fit:cover; border-radius:8px; border:1px solid var(--divider); cursor:zoom-in; display:block; }
  .att .att-x { position:absolute; top:-6px; right:-6px; width:18px; height:18px; border-radius:50%; background:var(--main-bg);
    border:1px solid var(--divider); color:var(--muted); font-size:11px; line-height:16px; text-align:center; cursor:pointer; }
  .att .att-x:hover { color:var(--red); }
  .att .att-cap { font-size:10.5px; color:var(--muted); margin-top:2px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .ec-drop { outline:2px dashed var(--accent); outline-offset:3px; }
  .ec-pills:empty { display:none; }
  .ec-pill { font-size:12.5px; padding:3px 10px; border-radius:13px; background:var(--chip-bg); color:var(--chip-fg);
    display:inline-flex; align-items:center; gap:5px; cursor:pointer; white-space:nowrap; }
  .ec-pill.when { color:var(--text); } .ec-pill.dl { color:var(--red); }
  .ec-pill svg { width:13px; height:13px; }
  .ec-checks { margin:8px 0 2px; line-height:1.85; }
  .ec-checks .ci { color:var(--muted); font-size:13px; } .ec-checks .ci.done { text-decoration:line-through; }
  .ec-editor { display:none; margin:8px 0 2px; padding:9px 0 2px; border-top:1px solid var(--divider); }
  .ec-editor.show { display:block; }
  .ec-editor .qchips { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:8px; }
  .ec-editor input { width:100%; font:inherit; color:var(--text); background:var(--side-bg);
    border:1px solid var(--divider); border-radius:8px; padding:7px 9px; }
  .ec-foot { display:flex; align-items:center; gap:2px; margin-top:11px; padding-top:10px; border-top:1px solid var(--divider); }
  .ec-tool { width:32px; height:30px; border:0; background:transparent; color:var(--muted); cursor:pointer;
    border-radius:7px; font-size:15px; display:flex; align-items:center; justify-content:center; }
  .ec-tool:hover { background:var(--row-hover); color:var(--text); }
  .ec-tool.on { background:var(--row-sel); color:var(--text); }
  .ec-foot .spacer { flex:1; }
  .ec-link { border:0; background:transparent; color:var(--muted); cursor:pointer; font:inherit; font-size:12.5px; padding:4px 8px; border-radius:7px; }
  .ec-link:hover { background:var(--row-hover); color:var(--text); }
  .ec-kind { margin:0 30px 12px 0; }
  .ec-where { color:var(--muted); font-size:12px; margin-right:8px; }
  .ec-add { padding:6px 16px; font-size:13px; }

  .org-row { border:1px solid var(--divider); border-radius:9px; padding:10px 12px; margin:8px 0; }
  .org-cur { color:var(--text); font-size:13px; font-weight:600; margin-bottom:6px; }
  .org-line { display:flex; gap:8px; align-items:flex-start; padding:3px 0; cursor:pointer; font-size:13px; }
  .org-line input { margin-top:3px; flex:0 0 auto; }
  .org-reason { color:var(--muted); font-size:11.5px; margin-top:4px; font-style:italic; }

  .col { background:var(--col-bg); border-radius:12px; width:300px; flex:0 0 300px; max-height:100%; display:flex; flex-direction:column; }
  .col-head { padding:13px 15px 9px; font-weight:600; font-size:13px; text-transform:uppercase;
    letter-spacing:.03em; color:var(--muted); display:flex; justify-content:space-between; }
  .col-cards { padding:0 9px 12px; overflow-y:auto; min-height:24px; }
  .col.drop { outline:2px dashed var(--accent); outline-offset:-4px; border-radius:12px; }
  .card { background:var(--card-bg); border-radius:9px; padding:11px 12px; margin:7px 0; box-shadow:var(--card-shadow); cursor:pointer; }
  .card.dragging { opacity:.4; }
  .card .ct { font-weight:600; margin-bottom:2px; }
  .card .csub { color:var(--muted); font-size:12px; }
  .card .cdesc { color:var(--muted); font-size:12px; margin-top:4px; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
  .card .cfoot { margin-top:9px; display:flex; align-items:center; gap:7px; color:var(--muted); font-size:12px; }
  .card .kind { font-size:10.5px; text-transform:uppercase; letter-spacing:.04em; border:1px solid var(--pill-border); border-radius:9px; padding:0 6px; }
  .crepos { margin-top:8px; display:flex; flex-wrap:wrap; gap:6px; align-items:center; }
  .cpulse { color:var(--muted); font-size:11px; margin-top:8px; }
  .crepos .repo { font-size:11px; color:var(--muted); border:1px solid var(--pill-border); border-radius:8px; padding:1px 3px 1px 8px; display:inline-flex; align-items:center; gap:1px; }
  .crepos .rb { border:0; background:transparent; cursor:pointer; color:var(--muted); font-size:12px; padding:0 4px; border-radius:5px; line-height:1.6; }
  .crepos .rb:hover { background:var(--row-hover); color:var(--text); }
  .crepos .rb.add { border:1px dashed var(--pill-border); border-radius:8px; padding:0 7px; }
  /* project/area list-view repo bar (same chips + pulse as a board card) */
  .proj-repos { margin:-6px 0 18px; }
  .proj-repos .cpulse { margin-top:6px; }

  .pri-wrap { display:flex; gap:16px; height:100%; }
  .pri-pool { width:300px; flex:0 0 300px; background:var(--col-bg); border-radius:12px; display:flex; flex-direction:column; }
  .matrix { flex:1; display:grid; grid-template-columns:1fr 1fr; grid-template-rows:1fr 1fr; gap:14px; min-width:0; }
  .quad { border:1px solid var(--divider); border-radius:12px; display:flex; flex-direction:column; min-height:0; }
  .quad-head { padding:11px 14px 8px; border-bottom:1px solid var(--divider); }
  .quad-head .qt { font-weight:700; } .quad-head .qs { color:var(--muted); font-size:12px; }
  .quad .cards { padding:8px 10px; overflow-y:auto; flex:1; }
  .quad.drop, .pri-pool.drop { outline:2px dashed var(--accent); outline-offset:-4px; }
  .q-do .quad-head .qt { color:var(--red); }
  .q-sched .quad-head .qt { color:#2e9e5b; }
  .q-deleg .quad-head .qt { color:#d98a1f; }
  .pcard { background:var(--card-bg); border-radius:8px; padding:8px 11px; margin:6px 0; box-shadow:var(--card-shadow); cursor:pointer; }
  .pcard.dragging { opacity:.4; } .pcard .pt { font-weight:500; }
  .pcard .psub { color:var(--muted); font-size:12px; margin-top:2px; }

  /* Priority Levels: a 2×2 grid (P1 P2 / P3 P4), tasks bucketed by Things tags */
  .levels { flex:1; display:grid; grid-template-columns:1fr 1fr; grid-template-rows:1fr 1fr; gap:14px; min-width:0; }
  .lvl { border:1px solid var(--divider); border-radius:12px; display:flex; flex-direction:column; min-height:0; border-left:4px solid var(--muted); }
  .lvl-head { padding:9px 14px; border-bottom:1px solid var(--divider); display:flex; align-items:baseline; gap:8px; }
  .lvl-head .lt { font-weight:700; } .lvl-head .ls { color:var(--muted); font-size:12px; } .lvl-head .lc { margin-left:auto; color:var(--muted); font-size:12px; }
  .lvl .cards { padding:8px 10px; overflow-y:auto; flex:1; }
  .lvl.drop, .levels .pri-pool.drop { outline:2px dashed var(--accent); outline-offset:-4px; }
  .lvl-1 { border-left-color:#e0402b; } .lvl-1 .lt { color:#e0402b; }
  .lvl-2 { border-left-color:#d98a1f; } .lvl-2 .lt { color:#d98a1f; }
  .lvl-3 { border-left-color:#2e9e5b; } .lvl-3 .lt { color:#2e9e5b; }
  .lvl-4 { border-left-color:#4c8dff; } .lvl-4 .lt { color:#4c8dff; }
  .lvl-mapnote { color:var(--muted); font-size:12px; padding:14px; text-align:center; }
  .lvl-tagrow { display:flex; gap:8px; align-items:center; margin:7px 0; }
  .lvl-tagrow .lbl { flex:0 0 96px; font-weight:600; } .lvl-tagrow input { flex:1; }

  /* Per-area header toggle: same muted segmented-control look as the view switcher.
     A single segment that reads "pressed in" (white + shadow) when roll-up is on. */
  .rollup-tog { margin-right:10px; }
  .rollup-tog .vt::before { content:""; display:inline-block; width:13px; height:13px; margin-right:6px; vertical-align:-2px; border-radius:3px; border:1.5px solid var(--check-border); box-sizing:border-box; background:no-repeat center/9px; }
  .rollup-tog .vt.on::before { border-color:var(--muted); background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12'><path d='M2.5 6.2 5 8.7l4.5-5' fill='none' stroke='%238a8f98' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'/></svg>"); }

  .overlay { position:fixed; inset:0; background:var(--overlay); display:none; align-items:flex-start; justify-content:center; z-index:20; padding:60px 16px; }
  .overlay.show { display:flex; }
  .panel { background:var(--main-bg); border-radius:14px; width:520px; max-width:100%; max-height:84vh; overflow-y:auto; box-shadow:0 16px 50px rgba(0,0,0,.35); padding:22px 24px; }
  .panel h2 { margin:0 0 4px; font-size:18px; } .panel .sub { color:var(--muted); font-size:12px; margin-bottom:16px; }
  .field { margin-bottom:14px; } .field label { display:block; font-size:12px; color:var(--muted); margin-bottom:5px; }
  .field input:not([type=checkbox]), .field textarea { width:100%; font:inherit; color:var(--text); background:var(--side-bg); border:1px solid var(--divider); border-radius:8px; padding:8px 10px; }
  .field input[type=checkbox] { width:16px; height:16px; flex:0 0 16px; margin:0; }
  .field textarea { min-height:80px; resize:vertical; }
  .checks { margin:8px 0 0; line-height:1.8; } .checks .ci { color:var(--muted); font-size:13px; } .checks .ci.done { text-decoration:line-through; }
  .btnrow { display:flex; gap:8px; flex-wrap:wrap; margin-top:18px; align-items:center; }
  .btn { font:inherit; padding:7px 15px; border-radius:8px; border:1px solid var(--divider); background:var(--main-bg); color:var(--text); cursor:pointer; }
  .btn:hover { background:var(--row-hover); } .btn.primary { background:var(--accent); border-color:var(--accent); color:#fff; }
  .btn.danger { color:var(--red); } .btn.ghost { border:0; color:var(--muted); } .spacer { flex:1; }
  .hint { font-size:12px; color:var(--muted); margin-top:6px; } .hint.warn { color:var(--red); }
  .col-edit { display:flex; gap:6px; margin:5px 0; align-items:center; } .col-edit input { flex:1; }
  .col-edit.dragging { opacity:.4; }
  .col-edit .drag { cursor:grab; color:var(--muted); user-select:none; padding:0 2px; font-size:13px; }
  .area-pick { font-weight:600; margin:12px 0 4px; } .proj-pick { padding-left:18px; }
  .pick { display:flex; align-items:center; gap:8px; padding:3px 0; cursor:pointer; font-weight:400; }
  .repo-row { display:flex; gap:6px; margin:6px 0; align-items:center; }
  .repo-row .rr-label { flex:0 0 130px; } .repo-row .rr-path { flex:1; } .repo-row .rr-gh { flex:0 0 160px; }
</style>
</head>
<body>
<div class="topbar">
  <div class="brand">SUUR THINGS</div>
  <button id="cmdk-btn" class="cmdk-btn" onclick="openCmdk()" title="Search & commands (⌘K)">
    <svg viewBox="0 0 16 16"><g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><circle cx="6.8" cy="6.8" r="4.1"/><path d="M9.9 9.9 14 14"/></g></svg>
    <span class="ck-ph">Search &amp; commands</span><span class="kbd">⌘K</span>
  </button>
  <span class="grow"></span>
  <button class="iconbtn" id="add-btn" title="Add to-do or project" onclick="openCreate('todo')">＋</button>
  <button class="iconbtn" id="prefs-btn" title="Preferences" onclick="openPrefs()">⚙</button>
  <button class="iconbtn" id="theme" title="Toggle light/dark">◐</button>
</div>
<div class="views">
  <aside class="sidebar" id="sidebar">
    <div class="side-nav" id="side-nav"></div>
    <button class="side-foot" id="about-link" onclick="go('#about')">
      <svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="8" cy="5.1" r="0.95" fill="currentColor"/><rect x="7.2" y="6.9" width="1.6" height="4.8" rx="0.8" fill="currentColor"/></svg>
      <span>About · Credits</span>
    </button>
  </aside>
  <main class="main">
    <div class="main-head">
      <span class="ico" id="head-ico">⭐</span><h1 id="head-title">Today</h1>
      <span class="grow"></span>
      <div class="viewtog rollup-tog" id="rollup-pill" style="display:none" title="Fold this area's project tasks into the view">
        <button class="vt" id="rollup-vt" onclick="toggleRollupPill()">Project tasks</button>
      </div>
      <div class="viewtog" id="viewtog">
        <button class="vt" id="vt-list" onclick="setListView('list')">List</button>
        <button class="vt" id="vt-matrix" onclick="setListView('matrix')">Matrix</button>
        <button class="vt" id="vt-levels" onclick="setListView('levels')">Levels</button>
        <button class="vt" id="vt-cards" onclick="setListView('cards')">Cards</button>
        <button class="vt" id="vt-timeline" onclick="setListView('timeline')">Timeline</button>
      </div>
      <button class="iconbtn" id="organize-btn" title="Auto-organize this folder with your agent" style="display:none" onclick="startOrganize()">✨</button>
      <button class="iconbtn" id="board-gear" title="Board settings" style="display:none" onclick="openBoardSettings()">⚙</button>
      <button class="iconbtn" id="levels-gear" title="Map Things tags to priority levels" style="display:none" onclick="openLevelMap()">⚙</button>
    </div>
    <div class="filterbar" id="filterbar"></div>
    <div id="content"></div>
  </main>
</div>

<div class="overlay" id="edit-overlay">
  <div class="editcard">
    <span class="ec-x" title="Close (saves changes)" onclick="closeEdit()">✕</span>
    <div class="viewtog ec-kind" id="ec-kind" style="display:none">
      <button class="vt on" data-kind="todo" onclick="setEditKind('todo')">To-Do</button>
      <button class="vt" data-kind="project" onclick="setEditKind('project')">Project</button>
    </div>
    <div class="ec-top">
      <span class="ec-box" id="ec-box" title="Complete" onclick="completeTask()"></span>
      <textarea class="ec-title" id="f-title" rows="1" placeholder="New To-Do" oninput="autoGrow(this)"></textarea>
    </div>
    <textarea class="ec-notes" id="f-notes" placeholder="Notes" oninput="autoGrow(this)"></textarea>
    <div class="ec-pills" id="ec-pills"></div>
    <div id="f-checklist"></div>
    <div id="ec-attach" class="ec-attach"></div>
    <input type="file" id="att-input" accept="image/png,image/jpeg,image/gif,image/webp,image/heic,image/heif" multiple style="display:none" onchange="onAttachPick(event)">
    <div class="ec-editor" id="ed-when">
      <div class="qchips" id="when-chips"></div>
      <input id="f-when" placeholder="today · evening · tomorrow · anytime · someday · yyyy-mm-dd" oninput="buildWhenChips();updatePills()">
    </div>
    <div class="ec-editor" id="ed-deadline">
      <input id="f-deadline" type="date" onchange="updatePills()">
    </div>
    <div class="ec-editor" id="ed-tags">
      <input id="f-tags" placeholder="comma, separated, tags" oninput="updatePills()">
    </div>
    <div class="hint warn" id="edit-warn" style="display:none">Read-only: set THINGS_AUTH_TOKEN to edit.</div>
    <div class="ec-foot">
      <button class="ec-tool" id="tool-when" title="When" onclick="toggleEditor('ed-when',this)">📅</button>
      <button class="ec-tool" id="tool-deadline" title="Deadline" onclick="toggleEditor('ed-deadline',this)">⚑</button>
      <button class="ec-tool" title="Checklist (edit in Things)" onclick="openInThings()">☰</button>
      <button class="ec-tool" id="tool-tags" title="Tags" onclick="toggleEditor('ed-tags',this)">🏷</button>
      <button class="ec-tool" id="tool-attach" title="Attach image (Things can't store images — shown here; a file link is added to notes)" onclick="$('#att-input').click()">📎</button>
      <span class="spacer"></span>
      <span class="ec-where" id="ec-where" style="display:none"></span>
      <button class="ec-link" onclick="cancelTask()">Cancel task</button>
      <button class="ec-link" onclick="openInThings()">Open in Things ↗</button>
      <button class="btn primary ec-add" id="ec-add" style="display:none" onclick="createFromCard()">Add</button>
    </div>
  </div>
</div>

<div class="overlay" id="organize-overlay">
  <div class="panel" style="width:640px">
    <h2 id="org-title">✨ Organize folder</h2><div class="sub" id="org-sub">Your agent suggests improvements. Nothing is written until you Apply.</div>
    <div id="org-body"></div>
    <div class="btnrow" id="org-actions" style="display:none">
      <button class="btn primary" onclick="applyOrganize()">Apply selected</button>
      <span class="spacer"></span>
      <button class="btn ghost" onclick="closeOverlay('organize-overlay')">Close</button>
    </div>
  </div>
</div>

<div class="overlay" id="cmdk" style="align-items:flex-start; padding-top:84px">
  <div class="ck-panel">
    <input id="cmdk-input" placeholder="Search tasks or type a command…" autocomplete="off">
    <div class="ck-list" id="cmdk-list"></div>
  </div>
</div>


<div class="overlay" id="prefs-overlay">
  <div class="panel">
    <h2>Preferences</h2><div class="sub">How "Open in editor / terminal" launches. Saved locally.</div>
    <div class="field"><label>Editor command (on your PATH — e.g. code, cursor, subl, idea)</label><input id="pf-editor" placeholder="code"></div>
    <div class="field"><label>Terminal app (e.g. Ghostty, iTerm, Terminal, Warp)</label><input id="pf-terminal" placeholder="Terminal"></div>
    <div class="hint">Blank = defaults (editor falls back to Finder; terminal to Terminal.app).</div>
    <div class="btnrow"><button class="btn primary" onclick="savePrefs()">Save</button><span class="spacer"></span><button class="btn ghost" onclick="closeOverlay('prefs-overlay')">Cancel</button></div>
  </div>
</div>

<div class="overlay" id="levelmap-overlay">
  <div class="panel">
    <h2>Priority levels</h2><div class="sub">Map your existing Things tags to four levels. A task lands at the first level whose tags it carries. The first tag in each row is written back to Things when you drag a task into that level.</div>
    <div id="levelmap-rows"></div>
    <div class="hint">Comma-separate tags. Leave a level blank to skip it. Your known tags: <span id="levelmap-known"></span></div>
    <div class="btnrow"><button class="btn primary" onclick="saveLevelMap()">Save</button><span class="spacer"></span><button class="btn ghost" onclick="closeOverlay('levelmap-overlay')">Cancel</button></div>
  </div>
</div>

<div class="overlay" id="repos-overlay">
  <div class="panel">
    <h2 id="repos-title">Linked repos</h2><div class="sub">A project can have several (e.g. app + website). Changes save automatically.</div>
    <div id="repos-list"></div>
    <button class="btn" style="margin-top:6px" onclick="addRepoRow()">+ Add repo</button>
    <div class="btnrow"><button class="btn primary" onclick="closeOverlay('repos-overlay')">Done</button></div>
  </div>
</div>

<div class="overlay" id="settings-overlay">
  <div class="panel">
    <h2>Board settings</h2><div class="sub">Changes save automatically.</div>
    <div class="field"><label>Board name</label><input id="b-name" onchange="persistSettings()"></div>
    <div class="field">
      <label>Columns (project stages)</label>
      <div id="cols-edit"></div>
      <button class="btn" style="margin-top:6px" onclick="addCol()">+ Add column</button>
    </div>
    <div class="field">
      <label>Include — a whole area, or specific projects</label>
      <div id="includes"></div>
    </div>
    <div class="btnrow">
      <button class="btn primary" onclick="closeOverlay('settings-overlay')">Done</button>
      <span class="spacer"></span>
      <button class="btn danger" onclick="deleteBoard()">Delete board</button>
    </div>
  </div>
</div>

<script>
const $ = (s, r=document) => r.querySelector(s);
let AUTH=false, SIDEBAR=null, CONFIG={boards:[],priority:{},priority_levels:[],area_prefs:{}};
let MODE="list", CUR_BOARD=null, SEL=null, EDIT_ID=null, CURRENT_ID="today", TODAY_CACHE=[];
let LAST_ITEMS={}, ORG_SUG=[];
let COLLAPSED=new Set(JSON.parse(localStorage.getItem("collapsed-areas")||"[]"));
const DEFAULT_COLUMNS=["Backlog","In Progress","On Hold","Done"];
const QUADS=[
  {key:"do",title:"Do First",sub:"Urgent · Important",cls:"q-do"},
  {key:"schedule",title:"Schedule",sub:"Important · Not urgent",cls:"q-sched"},
  {key:"delegate",title:"Delegate",sub:"Urgent · Not important",cls:"q-deleg"},
  {key:"eliminate",title:"Don't Do",sub:"Neither",cls:"q-elim"},
];
// Flat single-colour glyphs in Things' real accent colours (replaces emoji).
const SVG={
  inbox:`<svg viewBox="0 0 16 16"><g fill="none" stroke="#4c8dff" stroke-width="1.35" stroke-linejoin="round" stroke-linecap="round"><path d="M2.8 9.3h2.3a2.9 2.9 0 0 0 5.8 0h2.3"/><path d="M2.8 9.3 4.05 3.95a1 1 0 0 1 .97-.77h5.96a1 1 0 0 1 .97.77L13.2 9.3v2.35a1 1 0 0 1-1 1H3.8a1 1 0 0 1-1-1z"/></g></svg>`,
  today:`<svg viewBox="0 0 16 16"><path fill="var(--gold)" d="M8 1.6l1.86 3.77 4.16.6-3.01 2.94.71 4.15L8 11.16l-3.72 1.9.71-4.15L1.98 5.97l4.16-.6z"/></svg>`,
  upcoming:`<svg viewBox="0 0 16 16"><g fill="#e0402b"><path d="M3.6 4.2h8.8a1.4 1.4 0 0 1 1.4 1.4V12a1.4 1.4 0 0 1-1.4 1.4H3.6A1.4 1.4 0 0 1 2.2 12V5.6a1.4 1.4 0 0 1 1.4-1.4z"/><rect x="4.7" y="2.4" width="1.3" height="3" rx=".65"/><rect x="10" y="2.4" width="1.3" height="3" rx=".65"/></g><circle cx="8" cy="9.6" r="1.45" fill="#fff"/></svg>`,
  anytime:`<svg viewBox="0 0 16 16"><g fill="#2bb3c0"><path d="M8 2.3l5.7 2.75L8 7.8 2.3 5.05z"/><path opacity=".82" d="M2.3 8.45 8 11.2l5.7-2.75-1.78-.86L8 9.45 4.08 7.59z"/></g></svg>`,
  someday:`<svg viewBox="0 0 16 16"><g fill="#b8973f"><path d="M3.4 3.1h9.2a1 1 0 0 1 .99 1.16L13.3 5.7H2.7l-.18-1.44A1 1 0 0 1 3.4 3.1z"/><path d="M3 7h10l-.5 5.05a1.1 1.1 0 0 1-1.1.99H4.6a1.1 1.1 0 0 1-1.1-.99z"/></g><rect x="6.3" y="8.7" width="3.4" height="1.25" rx=".6" fill="#fff"/></svg>`,
  logbook:`<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6.1" fill="#3fa34d"/><path d="M5.15 8.2 7 10.05l3.85-4" fill="none" stroke="#fff" stroke-width="1.55" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  trash:`<svg viewBox="0 0 16 16"><g fill="var(--muted)"><path d="M6.1 2.5h3.8a.8.8 0 0 1 .8.8V4H5.3v-.7a.8.8 0 0 1 .8-.8z"/><rect x="3.2" y="4.2" width="9.6" height="1.5" rx=".7"/><path d="M4.3 6.4h7.4l-.58 6.1a1.1 1.1 0 0 1-1.1 1H5.98a1.1 1.1 0 0 1-1.1-1z"/></g></svg>`,
  priority:`<svg viewBox="0 0 16 16"><g><rect x="2.4" y="2.4" width="4.8" height="4.8" rx="1.2" fill="#e0402b"/><rect x="8.8" y="2.4" width="4.8" height="4.8" rx="1.2" fill="var(--muted)"/><rect x="2.4" y="8.8" width="4.8" height="4.8" rx="1.2" fill="var(--muted)"/><rect x="8.8" y="8.8" width="4.8" height="4.8" rx="1.2" fill="var(--muted)"/></g></svg>`,
  levels:`<svg viewBox="0 0 16 16"><g><rect x="2.4" y="2.6" width="11.2" height="2.3" rx="1.15" fill="#e0402b"/><rect x="2.4" y="6.85" width="8.4" height="2.3" rx="1.15" fill="#d98a1f"/><rect x="2.4" y="11.1" width="5.2" height="2.3" rx="1.15" fill="var(--muted)"/></g></svg>`,
  image:`<svg viewBox="0 0 16 16"><g fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"><rect x="2.3" y="3.4" width="11.4" height="9.2" rx="1.6"/><circle cx="5.6" cy="6.6" r="1.05" fill="currentColor" stroke="none"/><path d="M2.9 11.6 6.1 8.7l2.1 1.9 2.4-2.7 2.5 2.7"/></g></svg>`,
  board:`<svg viewBox="0 0 16 16"><g fill="var(--muted)"><rect x="2.4" y="3" width="3.1" height="10" rx="1.2"/><rect x="6.45" y="3" width="3.1" height="7" rx="1.2"/><rect x="10.5" y="3" width="3.1" height="9" rx="1.2"/></g></svg>`,
  search:`<svg viewBox="0 0 16 16"><g fill="none" stroke="var(--muted)" stroke-width="1.6" stroke-linecap="round"><circle cx="6.8" cy="6.8" r="4.1"/><path d="M9.9 9.9 14 14"/></g></svg>`,
  info:`<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6.4" fill="none" stroke="var(--muted)" stroke-width="1.5"/><circle cx="8" cy="5" r="1" fill="var(--muted)"/><rect x="7.15" y="6.9" width="1.7" height="5" rx="0.85" fill="var(--muted)"/></svg>`,
};
const ABOUT_HTML=`<div class="about">
  <p class="lead">A local, Things-faithful dashboard and <a href="https://modelcontextprotocol.io" target="_blank" rel="noopener">MCP</a> server for <a href="https://culturedcode.com/things/" target="_blank" rel="noopener">Things 3</a> — so any AI agent can read and manage your tasks, and you get views Things doesn't have (project boards, an Eisenhower matrix, a cards view).</p>
  <h2>How it works</h2>
  <p><strong>Reads</strong> come straight from the local Things SQLite database (read-only) via the excellent <a href="https://github.com/thingsapi/things.py" target="_blank" rel="noopener">things.py</a>. <strong>Writes</strong> go <em>only</em> through the official Things URL Scheme — the path Cultured Code documents for automation. This server never writes the database directly, so it can't corrupt it. Boards and priority quadrants are local browser overlays (Things has no such concept); they never touch your Things data.</p>
  <h2>Thanks</h2>
  <ul>
    <li><strong>Cultured Code</strong> — for <a href="https://culturedcode.com/things/" target="_blank" rel="noopener">Things 3</a>, the task app this is built around, and for documenting a safe automation path.</li>
    <li><strong>things.py</strong> — the read layer that absorbs every schema quirk.</li>
    <li><strong>Model Context Protocol</strong> — the open standard that lets any agent connect.</li>
  </ul>
  <h2>Who</h2>
  <p>Built by <strong>Artyom Sklyarov</strong> at <a href="https://suur.io" target="_blank" rel="noopener">SUUR</a> — an indie studio. Free and open source (MIT).</p>
  <p><a href="https://github.com/artyomsklyarov/suur-things-mcp" target="_blank" rel="noopener">github.com/artyomsklyarov/suur-things-mcp</a> · <a href="https://suur.io" target="_blank" rel="noopener">suur.io</a></p>
  <p class="muted">An agent connected here can read your to-do and note content, which is sent to whatever model you use. Nothing here phones home — no telemetry, no bundled model. "Things" is a trademark of Cultured Code GmbH &amp; Co. KG; this is an independent, unofficial project, not affiliated with or endorsed by Cultured Code.</p>
</div>`;
function findProject(id){
  for(const a of ((SIDEBAR&&SIDEBAR.areas)||[])){ const p=a.projects.find(p=>p.uuid===id); if(p) return p; }
  for(const p of ((SIDEBAR&&SIDEBAR.arealess)||[])){ if(p.uuid===id) return p; }
  return null;
}
function resolveDestId(name){  // triage: map an agent-proposed destination NAME → project/area uuid
  name=(name||"").trim().toLowerCase(); if(!name) return null;
  for(const a of ((SIDEBAR&&SIDEBAR.areas)||[])){
    if((a.title||"").trim().toLowerCase()===name) return a.uuid;
    for(const p of a.projects){ if((p.title||"").trim().toLowerCase()===name) return p.uuid; }
  }
  for(const p of ((SIDEBAR&&SIDEBAR.arealess)||[])){ if((p.title||"").trim().toLowerCase()===name) return p.uuid; }
  return null;
}
function setHeadIcon(sel){
  const el=$("#head-ico");
  if(sel.kind==="builtin" && SVG[sel.id]){ el.innerHTML=SVG[sel.id]; return; }
  if(sel.kind==="project"){ const p=findProject(sel.id); el.innerHTML=p?ring(p.progress):""; return; }
  el.textContent="";  // areas show their name large, no glyph (matches Things)
}
function esc(s){ return String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
// Centralized fetch wrappers: every call used to be an inline fetch().json()
// with no catch, so a thrown fetch (network drop, server restart) failed silently —
// stale spinners, "nothing happened". These never throw: on any network/parse error
// they return {ok:false, error} so call sites' existing `if(!r.ok)` handles it.
async function getJSON(url){
  try{ const res = await fetch(url); return await res.json(); }
  catch(e){ return {ok:false, error:(e&&e.message)||String(e), _neterr:true}; }
}
async function postJSON(url, body){
  try{
    const res = await fetch(url, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)});
    return await res.json();
  }catch(e){ return {ok:false, error:(e&&e.message)||String(e), _neterr:true}; }
}
// Safe to drop into a single-quoted JS string inside an inline on*="" handler.
// encodeURIComponent escapes <>&" and most metachars but NOT the apostrophe, which
// is exactly the string delimiter — so a title like  '+code+'  would break out and
// execute. Escaping ' to %27 closes that hole; the receiver decodeURIComponent's it back.
function jsarg(s){ return encodeURIComponent(String(s)).replace(/'/g,"%27"); }
// Linkify full URLs (https://…) and bare domains (hrv.suur.io, www.x.com/path).
// The bare-domain pass skips anything preceded by / @ . " ' > (already-linked URLs,
// emails) and skips common file extensions so "config.py" isn't turned into a link.
const _NOT_DOMAIN=new Set(["py","js","ts","tsx","jsx","md","json","txt","sh","css","html","png","jpg","jpeg","svg","gif","go","rs","rb","yml","yaml","toml","lock"]);
function _anchor(href,text){ return '<a href="'+href+'" target="_blank" rel="noopener">'+text+'</a>'; }
function linkify(s){
  // Protect full URLs as placeholders first, so the bare-domain pass below can't
  // re-match the domain inside an href we just emitted. Restore them at the end.
  const urls=[];
  let h=esc(s).replace(/(https?:\\/\\/[^\\s<]+)/g, u=>{ urls.push(u); return "\\u0001"+(urls.length-1)+"\\u0001"; });
  h=h.replace(/(^|[^\\/@."'\\u0001])((?:www\\.)?(?:[a-z0-9-]+\\.)+[a-z]{2,})((?:\\/[^\\s<]*)?)(?=[\\s<).,!?]|$)/gi,
    (m,pre,host,path)=>{ if(_NOT_DOMAIN.has(host.split(".").pop().toLowerCase())) return m;
      return pre+_anchor("https://"+host+path, host+path); });
  return h.replace(/\\u0001(\\d+)\\u0001/g, (m,i)=>_anchor(urls[+i], urls[+i]));
}
function uid(){ return Math.random().toString(36).slice(2,10); }

function applyTheme(t){ document.documentElement.setAttribute("data-theme",t); $("#theme").textContent=t==="dark"?"☀":"☾"; localStorage.setItem("things-theme",t); }
applyTheme(localStorage.getItem("things-theme") || (matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"));
$("#theme").onclick=()=>applyTheme(document.documentElement.getAttribute("data-theme")==="dark"?"light":"dark");

function ring(p){ const r=6,c=2*Math.PI*r,off=c*(1-p);
  if(p<=0) return `<svg class="ring" width="16" height="16" viewBox="0 0 16 16"><circle class="ring-bg" cx="8" cy="8" r="6"/></svg>`;
  return `<svg class="ring" width="16" height="16" viewBox="0 0 16 16"><circle class="ring-bg" cx="8" cy="8" r="6"/><circle class="ring-fg" cx="8" cy="8" r="6" stroke-dasharray="${c.toFixed(2)}" stroke-dashoffset="${off.toFixed(2)}" transform="rotate(-90 8 8)"/></svg>`; }

async function loadConfig(){ CONFIG=(await getJSON("/api/config")).config; }
// Save only the sections this client owns in this action, so a concurrent edit
// (CLI / another tab) to a different section is never clobbered.
async function saveConfig(){
  const r=await postJSON("/api/config", {boards:CONFIG.boards, priority:CONFIG.priority});
  if(r.ok) CONFIG=r.config;
}
async function saveItemRepos(itemId, kind, repos){
  const r=await postJSON("/api/link", {item_id:itemId, kind, repos});
  if(r.ok) CONFIG=r.config;
}

// --- navigation (hash-based, Back/Forward works) ---
function go(h){ if(location.hash===h) route(); else location.hash=h; }
function route(){
  const h=location.hash;
  $("#levels-gear").style.display="none";   // only the Priority Levels view shows it
  $("#rollup-pill").style.display="none";    // only area list views show it (renderList re-shows)
  if(h==="#about") return renderAbout();
  if(h==="#pl") return renderLevels();
  if(h==="#p") return renderPriority();
  if(h.startsWith("#b/")){ const id=decodeURIComponent(h.slice(3)); if(CONFIG.boards.find(b=>b.id===id)) return renderBoard(id); }
  if(h.startsWith("#l/")){ let rest=h.slice(3); let view="list";
    if(rest.endsWith("/m")){ view="matrix"; rest=rest.slice(0,-2); }
    else if(rest.endsWith("/p")){ view="levels"; rest=rest.slice(0,-2); }
    else if(rest.endsWith("/c")){ view="cards"; rest=rest.slice(0,-2); }
    else if(rest.endsWith("/t")){ view="timeline"; rest=rest.slice(0,-2); }
    const sel=resolveList(decodeURIComponent(rest)); if(sel) return renderList(sel, view); }
  return go("#l/today");
}
window.addEventListener("hashchange", route);

// --- ⌘K command palette (replaces the search box: navigate + search + create + view) ---
let CK_ITEMS=[], CK_SEL=0, CK_T=null, CK_MODE="main", CK_BASE=[];
function fuzzy(q,s){ if(!q) return true; q=q.toLowerCase(); s=(s||"").toLowerCase(); let i=0; for(let j=0;j<s.length&&i<q.length;j++){ if(s[j]===q[i]) i++; } return i===q.length; }
function ckCommands(){
  const out=[];
  ((SIDEBAR&&SIDEBAR.builtins)||[]).forEach(b=>out.push({label:b.title, hint:"Go", icon:SVG[b.id]||"", run:()=>go("#l/"+encodeURIComponent(b.id))}));
  out.push({label:"Priority Matrix", hint:"Go", icon:SVG.priority, run:()=>go("#p")});
  out.push({label:"Priority Levels", hint:"Go", icon:SVG.levels, run:()=>go("#pl")});
  (CONFIG.boards||[]).forEach(b=>out.push({label:b.name, hint:"Board", icon:SVG.board, run:()=>go("#b/"+encodeURIComponent(b.id))}));
  ((SIDEBAR&&SIDEBAR.areas)||[]).forEach(a=>a.projects.forEach(p=>out.push({label:p.title, hint:"Project", icon:"", run:()=>go("#l/"+encodeURIComponent(p.uuid))})));
  ((SIDEBAR&&SIDEBAR.arealess)||[]).forEach(p=>out.push({label:p.title, hint:"Project", icon:"", run:()=>go("#l/"+encodeURIComponent(p.uuid))}));
  out.push({label:"New to-do…", hint:"Create", icon:"", run:()=>{closeCmdk(); openCreate("todo");}});
  out.push({label:"New project…", hint:"Create", icon:"", run:()=>{closeCmdk(); openCreate("project");}});
  out.push({label:"New board", hint:"Create", icon:"", run:()=>{closeCmdk(); newBoard();}});
  out.push({label:"Organize this list ✨", hint:"Agent", icon:"", run:()=>{ if(SEL){ closeCmdk(); startOrganize(SEL.id,"organize"); } else alert("Open a list first."); }});
  out.push({label:"Triage Inbox ✨", hint:"Agent", icon:"", run:()=>{ closeCmdk(); startOrganize("inbox","triage"); }});
  out.push({label:"Calm my Today ✨", hint:"Agent", icon:"", run:()=>{ closeCmdk(); startOrganize("today","calm"); }});
  if(SEL && MODE!=="board" && MODE!=="about"){ [["list","List"],["matrix","Matrix"],["levels","Levels"],["cards","Cards"],["timeline","Timeline"]].forEach(([v,l])=>out.push({label:"Switch to "+l+" view", hint:"View", icon:"", run:()=>{closeCmdk(); setListView(v);}})); }
  out.push({label:"Toggle light / dark", hint:"App", icon:"", run:()=>{ $("#theme").click(); }});
  out.push({label:"Preferences", hint:"App", icon:"", run:()=>{closeCmdk(); openPrefs();}});
  out.push({label:"About · Credits", hint:"App", icon:SVG.info, run:()=>{closeCmdk(); go("#about");}});
  return out;
}
function openCmdk(){ CK_MODE="main"; openOverlay("cmdk"); const i=$("#cmdk-input"); i.value=""; ckRender(""); setTimeout(()=>i.focus(),0); }
function closeCmdk(){ closeOverlay("cmdk"); }
function ckRender(q){
  if(CK_MODE==="sub"){ CK_ITEMS = q ? CK_BASE.filter(c=>c._back||fuzzy(q,c.label)) : CK_BASE.slice(); CK_SEL=0; ckDraw(); return; }
  const all=ckCommands();
  let base;
  if(q){ base = all.filter(c=>fuzzy(q,c.label)); }
  else {  // curated default so the useful commands (incl. the agent ones) are discoverable
    const want=["New to-do…","New project…","Calm my Today ✨","Triage Inbox ✨","Organize this list ✨","Today","Inbox","Priority Matrix","About · Credits"];
    const by={}; all.forEach(c=>{ if(!(c.label in by)) by[c.label]=c; });
    base = want.map(l=>by[l]).filter(Boolean);
  }
  CK_ITEMS=base; CK_SEL=0; ckDraw();
  if(q.length>=2){
    clearTimeout(CK_T);
    CK_T=setTimeout(async()=>{
      if(CK_MODE!=="main" || $("#cmdk-input").value.trim()!==q) return;
      try{
        const d=await getJSON("/api/search?q="+encodeURIComponent(q));
        if(!d.ok || CK_MODE!=="main" || $("#cmdk-input").value.trim()!==q) return;
        const tasks=(d.items||[]).slice(0,8).map(it=>({label:it.title||"(untitled)", hint:it.project_title?("Task · "+it.project_title):"Task", icon:"", run:()=>enterTaskScreen({uuid:it.uuid,title:it.title,project_title:it.project_title})}));
        CK_ITEMS=base.concat(tasks); ckDraw();
      }catch(e){}
    },200);
  }
}
// --- ⌘K v2: act on a task found in the palette (keyboard-only, two-level) ---
function ckSub(items){ CK_MODE="sub"; CK_BASE=items; const i=$("#cmdk-input"); i.value=""; ckRender(""); i.focus(); }
function backToMain(){ CK_MODE="main"; const i=$("#cmdk-input"); i.value=""; ckRender(""); i.focus(); }
function enterTaskScreen(t){
  ckSub([
    {label:"← Back", _back:true, run:backToMain},
    {label:"Open in card", hint:t.title, run:()=>{closeCmdk(); openEdit(t.uuid);}},
    {label:"✓ Complete", run:()=>{ applyStatus(t.uuid,"completed").then(ok=>{ if(ok){ closeCmdk(); setTimeout(route,300);} }); }},
    {label:"Schedule → Today", run:()=>{closeCmdk(); reschedule(t.uuid,"today");}},
    {label:"Schedule → Tomorrow", run:()=>{closeCmdk(); reschedule(t.uuid,"tomorrow");}},
    {label:"Schedule → Anytime", run:()=>{closeCmdk(); reschedule(t.uuid,"anytime");}},
    {label:"Schedule → Someday", run:()=>{closeCmdk(); reschedule(t.uuid,"someday");}},
    {label:"Move to project…", run:()=>enterMoveScreen(t)},
  ]);
}
function enterMoveScreen(t){
  const targets=[{label:"← Back", _back:true, run:()=>enterTaskScreen(t)}];
  ((SIDEBAR&&SIDEBAR.areas)||[]).forEach(a=>{
    targets.push({label:a.title, hint:"Area", run:()=>{closeCmdk(); moveTask(t.uuid,a.uuid);}});
    a.projects.forEach(p=>targets.push({label:"   "+p.title, hint:"Project · "+a.title, run:()=>{closeCmdk(); moveTask(t.uuid,p.uuid);}}));
  });
  ((SIDEBAR&&SIDEBAR.arealess)||[]).forEach(p=>targets.push({label:p.title, hint:"Project", run:()=>{closeCmdk(); moveTask(t.uuid,p.uuid);}}));
  ckSub(targets);
}
async function moveTask(id, listId){
  if(!AUTH){ alert("Set THINGS_AUTH_TOKEN to move tasks."); return; }
  const r=await postJSON("/api/update", {id, list_id:listId});
  if(!r.ok){ alert("Move failed: "+(r.error||"")); return; }
  loadSidebar(); setTimeout(route,300);
}
function ckDraw(){
  const box=$("#cmdk-list"); box.innerHTML="";
  if(!CK_ITEMS.length){ box.innerHTML=`<div class="empty" style="padding:16px">No matches</div>`; return; }
  CK_ITEMS.forEach((c,i)=>{
    const row=document.createElement("div"); row.className="ck-row"+(i===CK_SEL?" sel":"");
    row.innerHTML=`<span class="ck-ico">${c.icon||""}</span><span class="ck-label">${esc(c.label)}</span><span class="ck-hint">${esc(c.hint||"")}</span>`;
    row.addEventListener("mousedown",e=>{ e.preventDefault(); c.run(); });
    row.addEventListener("mouseenter",()=>{ CK_SEL=i; [...box.children].forEach((ch,j)=>ch.classList.toggle("sel",j===i)); });
    box.appendChild(row);
  });
}
function ckScroll(){ const box=$("#cmdk-list"), sel=box.children[CK_SEL]; if(sel) sel.scrollIntoView({block:"nearest"}); }
(()=>{ const i=$("#cmdk-input"); if(!i) return;
  i.addEventListener("input",e=>ckRender(e.target.value.trim()));
  i.addEventListener("keydown",e=>{
    if(e.key==="ArrowDown"){ e.preventDefault(); CK_SEL=Math.min(CK_SEL+1,CK_ITEMS.length-1); ckDraw(); ckScroll(); }
    else if(e.key==="ArrowUp"){ e.preventDefault(); CK_SEL=Math.max(CK_SEL-1,0); ckDraw(); ckScroll(); }
    else if(e.key==="Enter"){ e.preventDefault(); const c=CK_ITEMS[CK_SEL]; if(c) c.run(); }
    else if(e.key==="Escape" && CK_MODE==="sub"){ e.preventDefault(); e.stopPropagation(); backToMain(); }
  });
  document.addEventListener("keydown",e=>{ if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==="k"){ e.preventDefault(); openCmdk(); } });
})();

// --- sidebar ---
async function loadSidebar(){
  const data=await getJSON("/api/sidebar");
  AUTH=!!data.auth; if(!data.ok){ $("#sidebar").innerHTML=`<div class="err">${esc(data.error||"error")}</div>`; return; }
  SIDEBAR=data.sidebar; renderSidebar();
}
function renderSidebar(){
  const el=$("#side-nav"); el.innerHTML="";
  const bi=SIDEBAR.builtins, tIdx=bi.findIndex(b=>b.id==="today");
  bi.slice(0,tIdx+1).forEach(b=>el.appendChild(builtinEl(b)));
  const pri=document.createElement("div"); pri.className="nav-item"; pri.dataset.id="priority";
  pri.innerHTML=`<span class="ico">${SVG.priority}</span><span class="label">Priority Matrix</span>`; pri.onclick=()=>go("#p");
  el.appendChild(pri);
  const lvl=document.createElement("div"); lvl.className="nav-item"; lvl.dataset.id="levels";
  lvl.innerHTML=`<span class="ico">${SVG.levels}</span><span class="label">Priority Levels</span>`; lvl.onclick=()=>go("#pl");
  el.appendChild(lvl);
  const gh=document.createElement("div"); gh.className="group-head";
  gh.innerHTML=`<span>Boards</span><span class="add" title="New board">＋</span>`;
  gh.querySelector(".add").onclick=(e)=>{e.stopPropagation(); newBoard();};
  el.appendChild(gh);
  CONFIG.boards.forEach(b=>{
    const row=document.createElement("div"); row.className="nav-item"; row.dataset.id=b.id;
    row.innerHTML=`<span class="ico">${SVG.board}</span><span class="label">${esc(b.name)}</span>`;
    row.onclick=()=>go("#b/"+encodeURIComponent(b.id)); el.appendChild(row);
  });
  bi.slice(tIdx+1).filter(b=>!["logbook","trash"].includes(b.id)).forEach(b=>el.appendChild(builtinEl(b)));
  el.appendChild(Object.assign(document.createElement("div"),{className:"nav-sep"}));
  const areas=SIDEBAR.areas.concat(SIDEBAR.arealess.length?[{uuid:null,title:"Projects",projects:SIDEBAR.arealess}]:[]);
  for(const a of areas){
    const collapsible=!!a.uuid, collapsed=collapsible&&COLLAPSED.has(a.uuid);
    const head=document.createElement("div"); head.className="area-head"; if(a.uuid) head.dataset.id=a.uuid;
    head.innerHTML=`<span class="chev">${collapsible?(collapsed?"▶":"▼"):""}</span><span class="label">${esc(a.title)}</span>`;
    if(collapsible){
      head.querySelector(".chev").onclick=(e)=>{e.stopPropagation(); toggleArea(a.uuid);};
      head.onclick=()=>go("#l/"+encodeURIComponent(a.uuid));
    }
    el.appendChild(head);
    if(!collapsed) for(const p of a.projects){
      const row=document.createElement("div"); row.className="project"; row.dataset.id=p.uuid;
      row.innerHTML=`${ring(p.progress)}<span class="label">${esc(p.title)}</span>`;
      row.onclick=()=>go("#l/"+encodeURIComponent(p.uuid)); el.appendChild(row);
    }
  }
  el.appendChild(Object.assign(document.createElement("div"),{className:"side-sep"}));
  bi.filter(b=>["logbook","trash"].includes(b.id)).forEach(b=>el.appendChild(builtinEl(b)));  // Logbook + Trash last
  setActive(CURRENT_ID);
}
function toggleArea(uuid){ COLLAPSED.has(uuid)?COLLAPSED.delete(uuid):COLLAPSED.add(uuid);
  localStorage.setItem("collapsed-areas", JSON.stringify([...COLLAPSED])); renderSidebar(); }
function builtinEl(b){
  const row=document.createElement("div"); row.className="nav-item"; row.dataset.id=b.id;
  const ic=SVG[b.id]||esc(b.icon||"");
  row.innerHTML=`<span class="ico">${ic}</span><span class="label">${esc(b.title)}</span>`+(b.count!=null?`<span class="count">${b.count}</span>`:"");
  row.onclick=()=>go("#l/"+encodeURIComponent(b.id));
  if(["today","anytime","someday"].includes(b.id)){  // drop a task here to reschedule (when=)
    row.addEventListener("dragover",e=>{ e.preventDefault(); row.classList.add("drop-when"); });
    row.addEventListener("dragleave",()=>row.classList.remove("drop-when"));
    row.addEventListener("drop",e=>{ e.preventDefault(); row.classList.remove("drop-when");
      const id=e.dataTransfer.getData("text/id"); if(id) reschedule(id, b.id); });
  }
  return row;
}
function setActive(id){ CURRENT_ID=id; document.querySelectorAll(".nav-item,.area-head,.project").forEach(n=>n.classList.toggle("active", n.dataset.id===String(id))); const al=$("#about-link"); if(al) al.classList.remove("active"); }
function resolveList(id){
  const bi=(SIDEBAR&&SIDEBAR.builtins)||[]; const b=bi.find(x=>x.id===id);
  if(b) return {id:b.id,icon:b.icon,title:b.title,kind:"builtin"};
  for(const a of (SIDEBAR.areas||[])){
    if(a.uuid===id) return {id:a.uuid,icon:"▥",title:a.title,kind:"area"};
    const p=a.projects.find(p=>p.uuid===id); if(p) return {id:p.uuid,icon:"",title:p.title,kind:"project"};
  }
  return null;
}

// --- list view ---
let LIST_ITEMS=[], LIST_KIND="", LIST_NOTES=null, CUR_FILTER=null, LIST_ROLLUP=true;
async function renderList(sel, view="list"){
  const matrix=view==="matrix", levels=view==="levels", cards=view==="cards", timeline=view==="timeline";
  MODE=view; CUR_BOARD=null; SEL=sel;
  $("#board-gear").style.display="none"; $("#levels-gear").style.display=levels?"flex":"none"; setActive(sel.id);
  $("#rollup-pill").style.display=(sel.kind==="area")?"inline-flex":"none";  // areas only, every view
  setHeadIcon(sel); $("#head-title").textContent=sel.title;
  setHeadEditable(sel.kind==="project"?"project":null, sel.id);
  $("#viewtog").classList.add("show");
  $("#vt-list").classList.toggle("on",view==="list"); $("#vt-matrix").classList.toggle("on",matrix); $("#vt-levels").classList.toggle("on",levels); $("#vt-cards").classList.toggle("on",cards); $("#vt-timeline").classList.toggle("on",timeline);
  $(".main").classList.toggle("fill", matrix||levels||timeline);
  const c=$("#content"); $("#filterbar").classList.remove("show"); c.innerHTML=`<div class="empty">loading…</div>`;
  const data=await getJSON("/api/items?id="+encodeURIComponent(sel.id));
  if(!data.ok){ c.innerHTML=`<div class="err">${esc(data.error||"error")}</div>`; return; }
  LIST_ITEMS=data.items; LIST_KIND=data.kind; LIST_NOTES=data.notes||null; CUR_FILTER=null; LIST_ROLLUP=data.rollup!==false;
  $("#rollup-vt").classList.toggle("on", LIST_KIND==="area" && LIST_ROLLUP);
  LAST_ITEMS={}; LIST_ITEMS.forEach(it=>{ LAST_ITEMS[it.uuid]=it.title; });
  $("#organize-btn").style.display=(view==="list"&&(LIST_KIND==="project"||LIST_KIND==="area"||sel.id==="inbox"))?"flex":"none";
  if(matrix){
    let items=LIST_ITEMS.slice();
    if(LIST_KIND==="area") items=areaProjects(sel.id).map(p=>({uuid:p.uuid,title:p.title,progress:p.progress,_proj:true})).concat(items);
    renderMatrix(items);
  } else if(levels){ renderLevelBands(); }
  else if(cards){ renderCards(LIST_ITEMS); }
  else if(timeline){ renderTimeline(LIST_ITEMS); }
  else { buildFilterBar(); renderRows(); }
}
function setListView(v){ if(SEL) go("#l/"+encodeURIComponent(SEL.id)+(v==="matrix"?"/m":v==="levels"?"/p":v==="cards"?"/c":v==="timeline"?"/t":"")); }
function areaProjects(areaId){ const a=((SIDEBAR&&SIDEBAR.areas)||[]).find(x=>x.uuid===areaId); return a?a.projects:[]; }
// Per-area header pill: fold in the area's project tasks, or show only its loose
// to-dos. Saved to the area_prefs config section; the server then decides what to
// return. Re-renders the *current* view (works on List/Matrix/Levels/Cards/Timeline).
function toggleRollupPill(){ setAreaRollup(!LIST_ROLLUP); }
async function setAreaRollup(on){
  if(!SEL) return;
  CONFIG.area_prefs=CONFIG.area_prefs||{}; CONFIG.area_prefs[SEL.id]={rollup:on};
  const r=await postJSON("/api/config", {area_prefs:CONFIG.area_prefs});
  if(r.ok) CONFIG=r.config;
  renderList(SEL, MODE);   // keep the current view; server includes/excludes tasks per the pref
}
function projCardEl(p){
  const el=document.createElement("div"); el.className="projcard";
  el.innerHTML=`${ring(p.progress||0)}<span class="pt">${esc(p.title)}</span>`;
  el.onclick=()=>go("#l/"+encodeURIComponent(p.uuid)); return el;
}
// --- cards view (YouTube thumbnails for link tasks) ---
function ytId(url){ if(!url) return null; const m=url.match(/(?:youtu\\.be\\/|youtube\\.com\\/(?:watch\\?v=|embed\\/|shorts\\/))([\\w-]{11})/); return m?m[1]:null; }
function renderCards(items){
  const c=$("#content"); c.innerHTML="";
  if(!items.length){ c.innerHTML=`<div class="empty">Nothing here.</div>`; return; }
  const grid=document.createElement("div"); grid.className="cardgrid";
  items.forEach(it=>grid.appendChild(taskCardEl(it))); c.appendChild(grid);
}
function taskCardEl(it){
  const el=document.createElement("div"); el.className="taskcard"+((it.status==="completed"||it.status==="canceled")?" is-done":"");
  el.onclick=()=>openEdit(it.uuid);
  const yt=ytId(it.link); let title=it.title||"";
  if(it.link){ title=title.replace(it.link,"").replace(/^\\s*watch:?\\s*/i,"").trim(); if(!title) title=yt?"YouTube video":it.link; }
  let h="";
  if(yt) h+=`<div class="thumb"><img loading="lazy" src="https://img.youtube.com/vi/${yt}/hqdefault.jpg" onerror="this.style.display='none'"><span class="play">▶</span></div>`;
  else if(it.link) h+=`<div class="thumb">🔗</div>`;
  h+=`<div class="tc-body"><div class="tc-title">${esc(title||"(untitled)")}</div>`+
     (it.project_title?`<div class="tc-sub">${esc(it.project_title)}</div>`:"")+
     ((it.tags&&it.tags.length)?`<div class="tc-tags">${it.tags.map(t=>`<span class="pill">${esc(t)}</span>`).join("")}</div>`:"")+
     `</div>`;
  el.innerHTML=h; return el;
}
function buildFilterBar(){
  const fb=$("#filterbar"); fb.innerHTML="";
  const tags=[...new Set(LIST_ITEMS.flatMap(it=>it.tags||[]))];
  if(!tags.length){ fb.classList.remove("show"); return; }
  fb.classList.add("show");
  fb.appendChild(chipEl("All", null));
  tags.forEach(t=>fb.appendChild(chipEl(t, t)));
}
function chipEl(label, tag){
  const c=document.createElement("div"); c.className="chip"+(CUR_FILTER===tag?" active":"");
  c.textContent=label;
  c.onclick=()=>{ CUR_FILTER=(CUR_FILTER===tag?null:tag); buildFilterBar(); renderRows(); };
  return c;
}
function renderRows(){
  const c=$("#content"); c.innerHTML="";
  if(LIST_NOTES){ const n=document.createElement("div"); n.className="proj-notes"; n.innerHTML=linkify(LIST_NOTES); c.appendChild(n); }
  // Linked repos + git/GitHub pulse, same as a board card — so a project/area shows
  // its repos even when it's not on any Kanban board.
  if((LIST_KIND==="project"||LIST_KIND==="area") && !CUR_FILTER){
    const repos=((CONFIG.links||{})[SEL.id]||{}).repos||[];
    const bar=document.createElement("div"); bar.className="proj-repos crepos";
    bar.innerHTML=repoChipsHtml(SEL.id, LIST_KIND, SEL.title, repos);
    c.appendChild(bar);
    if(repos.length) fetchPulse(SEL.id, bar);
  }
  const projs=(LIST_KIND==="area"&&!CUR_FILTER)?areaProjects(SEL.id):[];
  if(projs.length){ const g=document.createElement("div"); g.className="projcards"; projs.forEach(p=>g.appendChild(projCardEl(p))); c.appendChild(g); }
  let items=LIST_ITEMS;
  if(CUR_FILTER) items=items.filter(it=>(it.tags||[]).includes(CUR_FILTER));
  if(!items.length){ if(!projs.length){ const e=document.createElement("div"); e.className="empty"; e.textContent="Nothing here."; c.appendChild(e); } return; }
  const key=LIST_KIND==="project"?"heading_title":"project_title";
  const groups=groupBy(items,key).sort((a,b)=>(a.key?1:0)-(b.key?1:0));
  // For a project with headings, a "no heading" drop zone (visible only while dragging)
  // lets you pull a task back out to the top of the project.
  if(LIST_KIND==="project" && groups.some(g=>g.key)){
    const dz=document.createElement("div"); dz.className="heading-dropzone"; dz.textContent="Drop here for no heading (top of project)";
    headingDrop(dz, ""); c.appendChild(dz);
  }
  for(const g of groups){ if(g.key){ const h=document.createElement("div"); h.className="grp-head"; h.textContent=g.key;
    if(LIST_KIND==="project") headingDrop(h, g.key);   // drag a task onto a heading to move it there
    c.appendChild(h);} for(const it of g.items) c.appendChild(rowEl(it)); }
}
function groupBy(items,key){ const g=[],idx={};
  for(const it of items){ const k=it[key]||"\\u0000"; if(!(k in idx)){idx[k]=g.length; g.push({key:it[key]||null,items:[]});} g[idx[k]].items.push(it);} return g; }
// Drop a task row onto a project heading → move it under that heading (URL Scheme `heading`).
function headingDrop(el, heading){
  el.addEventListener("dragover",e=>{ e.preventDefault(); el.classList.add("drop"); });
  el.addEventListener("dragleave",()=>el.classList.remove("drop"));
  el.addEventListener("drop",e=>{ e.preventDefault(); el.classList.remove("drop");
    const id=e.dataTransfer.getData("text/id"); if(id) moveToHeading(id, heading); });
}
async function moveToHeading(uuid, heading){
  if(!AUTH){ alert("Set THINGS_AUTH_TOKEN to move tasks under a heading."); return; }
  const it=(LIST_ITEMS||[]).find(x=>x.uuid===uuid); if(it && (it.heading_title||"")===(heading||"")) return;  // already there (top == "")
  const r=await postJSON("/api/update", {id:uuid, heading});
  if(!r.ok){ alert("Move failed: "+(r.error||"")); return; }
  if(SEL) setTimeout(()=>renderList(SEL, MODE), 350);   // re-fetch so it shows under its new heading
}
function metaHtml(it){ let m="";
  if(((CONFIG.attachments||{})[it.uuid]||[]).length) m+=`<span class="att-ico" title="Has an image attachment">${SVG.image}</span>`;
  if(it.has_notes) m+=`<span class="note-ico">📄</span>`;
  (it.tags||[]).forEach(t=>m+=`<span class="pill">${esc(t)}</span>`);
  if(it.deadline){ const od=it.deadline<new Date().toISOString().slice(0,10); m+=`<span class="due">${od?'<span class="dot"></span>':"⚑"} ${it.deadline}</span>`; }
  return m; }
function rowEl(it){
  const done=it.status==="completed",cancel=it.status==="canceled";
  const row=document.createElement("div"); row.className="row"+(done||cancel?" is-done":""); row.onclick=()=>openEdit(it.uuid);
  row.draggable=true;  // drag onto a sidebar bucket (Today/Anytime/Someday) to reschedule, or a heading to move
  row.addEventListener("dragstart",e=>{ e.dataTransfer.setData("text/id",it.uuid); row.classList.add("dragging"); document.body.classList.add("dragging-task"); });
  row.addEventListener("dragend",()=>{ row.classList.remove("dragging"); document.body.classList.remove("dragging-task"); });
  const m=metaHtml(it);
  row.innerHTML=`<span class="box ${done?"done":cancel?"cancel":""}"></span><span class="title">${esc(it.title||"(untitled)")}</span>`+(m?`<span class="meta">${m}</span>`:"");
  if(!done&&!cancel){ const box=row.querySelector(".box"); box.title="Complete"; box.style.cursor="pointer";
    box.onclick=(e)=>{ e.stopPropagation(); applyStatus(it.uuid,"completed").then(ok=>{ if(ok) rerenderCurrent(); }); }; }
  return row;
}

// --- board view ---
async function renderBoard(id){
  MODE="board"; CUR_BOARD=id; setActive(id);
  $(".main").classList.add("fill"); $("#board-gear").style.display="flex"; $("#organize-btn").style.display="none";
  $("#filterbar").classList.remove("show"); $("#viewtog").classList.remove("show");
  const b=CONFIG.boards.find(x=>x.id===id);
  $("#head-ico").innerHTML=SVG.board; $("#head-title").textContent=b?b.name:"Board";
  setHeadEditable(b?"board":null, b?b.id:null);
  const c=$("#content"); c.innerHTML=`<div class="empty">loading…</div>`;
  const data=await getJSON("/api/board?id="+encodeURIComponent(id));
  if(!data.ok){ c.innerHTML=`<div class="err">${esc(data.error||"error")}</div>`; return; }
  c.innerHTML="";
  const wrap=document.createElement("div"); wrap.className="board-wrap";
  if(!data.columns.length) wrap.innerHTML=`<div class="empty">No columns yet. Open ⚙ to add stages and include projects/areas.</div>`;
  for(const col of data.columns) wrap.appendChild(boardColEl(col,id));
  c.appendChild(wrap);
}
function boardColEl(col,boardId){
  const c=document.createElement("div"); c.className="col";
  c.innerHTML=`<div class="col-head"><span>${esc(col.title)}</span><span>${col.cards.length}</span></div>`;
  const list=document.createElement("div"); list.className="col-cards";
  for(const card of col.cards) list.appendChild(boardCardEl(card));
  c.addEventListener("dragover",e=>{ e.preventDefault(); c.classList.add("drop"); });
  c.addEventListener("dragleave",()=>c.classList.remove("drop"));
  c.addEventListener("drop",e=>{ e.preventDefault(); c.classList.remove("drop"); const id=e.dataTransfer.getData("text/id"); if(id) placeCard(boardId,id,col.name); });
  c.appendChild(list); return c;
}
function boardCardEl(card){
  const el=document.createElement("div"); el.className="card"; el.draggable=true;
  el.onclick=()=>go("#l/"+encodeURIComponent(card.id));
  el.addEventListener("dragstart",e=>{ e.dataTransfer.setData("text/id",card.id); el.classList.add("dragging"); });
  el.addEventListener("dragend",()=>el.classList.remove("dragging"));
  const repoHtml=repoChipsHtml(card.id, card.kind, card.title, card.repos);
  el.innerHTML=`<div class="ct">${esc(card.title)}</div>`+
    (card.area_title?`<div class="csub">${esc(card.area_title)}</div>`:"")+
    (card.desc?`<div class="cdesc">${esc(card.desc)}</div>`:"")+
    `<div class="cfoot"><span class="kind">${card.kind}</span>${ring(card.progress)}<span>${card.open} open${card.total?` / ${card.total}`:""}</span></div>`+
    `<div class="crepos">${repoHtml}</div>`;
  if((card.repos||[]).length) fetchPulse(card.id, el);
  return el;
}
// Repo chips (open in editor/terminal/github) + a "🔗 repos" manage button.
// Shared by board cards and the project/area list-view repo bar.
function repoChipsHtml(id, kind, title, repos){
  let h="";
  (repos||[]).forEach((r,i)=>{ const lbl=r.label||(r.github?r.github.split("/")[1]:"repo");
    h+=`<span class="repo">${esc(lbl)}`+
      `<button class="rb" title="Open in editor" onclick="event.stopPropagation();openRepo('${id}',${i},'editor')">⌨</button>`+
      `<button class="rb" title="Open in terminal" onclick="event.stopPropagation();openRepo('${id}',${i},'terminal')">❯</button>`+
      (r.github?`<button class="rb" title="Open on GitHub" onclick="event.stopPropagation();openRepo('${id}',${i},'github')">↗</button>`:"")+
      `</span>`; });
  h+=`<button class="rb add" title="Manage repos" onclick="event.stopPropagation();openReposModal('${id}','${kind}','${jsarg(title)}')">🔗 repos</button>`;
  return h;
}
async function fetchPulse(itemId, el){
  try{
    const d=await getJSON("/api/pulse?item_id="+encodeURIComponent(itemId));
    if(!d.ok || !(d.repos||[]).length) return;
    const lines=d.repos.map(r=>{
      const bits=[];
      if(r.commits_7d!=null) bits.push(`${r.commits_7d} commit${r.commits_7d===1?"":"s"}/wk`);
      if(r.last_commit) bits.push("last "+r.last_commit);
      if(r.open_prs!=null) bits.push(`${r.open_prs} open PR${r.open_prs===1?"":"s"}`);
      return bits.length?bits.join(" · "):null;
    }).filter(Boolean);
    if(lines.length){ const p=document.createElement("div"); p.className="cpulse"; p.textContent=lines.join("   ·   "); el.appendChild(p); }
  }catch(e){}
}
async function openRepo(itemId, idx, target){
  const r=await postJSON("/api/open", {item_id:itemId,repo_index:idx,target});
  if(!r.ok) alert("Open failed: "+(r.error||""));
}
let REPOS_ITEM=null;
function openReposModal(itemId, kind, titleEnc){
  REPOS_ITEM={id:itemId, kind};
  $("#repos-title").textContent = "Repos · " + decodeURIComponent(titleEnc);
  const list=$("#repos-list"); list.innerHTML="";
  const repos=((CONFIG.links||{})[itemId]||{}).repos||[];
  (repos.length?repos:[{}]).forEach(r=>list.appendChild(repoRow(r)));
  openOverlay("repos-overlay");
}
function repoRow(r){
  const d=document.createElement("div"); d.className="repo-row";
  d.innerHTML=`<input class="rr-label" placeholder="Label (e.g. iOS app)" value="${esc(r.label||"")}" onchange="persistRepos()">`+
    `<input class="rr-path" placeholder="/absolute/path/to/repo" value="${esc(r.repo||"")}" onchange="persistRepos()">`+
    `<input class="rr-gh" placeholder="owner/repo (optional)" value="${esc(r.github||"")}" onchange="persistRepos()">`+
    `<button class="btn ghost" title="Remove" onclick="this.parentElement.remove(); persistRepos()">✕</button>`;
  return d;
}
function addRepoRow(){ $("#repos-list").appendChild(repoRow({})); }
async function persistRepos(){
  if(!REPOS_ITEM) return;
  const repos=[...document.querySelectorAll("#repos-list .repo-row")].map(row=>({
    label: row.querySelector(".rr-label").value.trim()||null,
    repo:  row.querySelector(".rr-path").value.trim(),
    github:row.querySelector(".rr-gh").value.trim()||null,
  })).filter(r=>r.repo);
  await saveItemRepos(REPOS_ITEM.id, REPOS_ITEM.kind, repos);  // per-item, no clobber
  if(MODE==="board"&&CUR_BOARD) renderBoard(CUR_BOARD);
  else if(MODE==="list"&&SEL&&SEL.id===REPOS_ITEM.id) renderRows();  // refresh the project-page repo bar
}
async function placeCard(boardId,itemId,column){
  const b=CONFIG.boards.find(x=>x.id===boardId); if(!b) return;
  b.placements=b.placements||{};
  if(column) b.placements[itemId]=column; else delete b.placements[itemId];
  await saveConfig(); renderBoard(boardId);
}

// --- priority matrix (Eisenhower; a view over ANY list's tasks) ---
// Quadrant assignment lives in the global CONFIG.priority map keyed by task uuid,
// so a task's priority is the same wherever it appears (Today, its project, etc).
async function renderPriority(){
  MODE="matrix"; CUR_BOARD=null; setActive("priority");
  $(".main").classList.add("fill"); $("#board-gear").style.display="none"; $("#organize-btn").style.display="none";
  $("#filterbar").classList.remove("show"); $("#viewtog").classList.remove("show");
  $("#head-ico").innerHTML=SVG.priority; $("#head-title").textContent="Priority Matrix"; setHeadEditable(null);
  const c=$("#content"); c.innerHTML=`<div class="empty">loading…</div>`;
  const data=await getJSON("/api/items?id=today");
  LIST_ITEMS=data.ok?data.items:[]; LIST_KIND="builtin"; renderMatrix(LIST_ITEMS);
}
function renderMatrix(items){
  const c=$("#content"); c.innerHTML="";
  const pr=CONFIG.priority||{};
  const wrap=document.createElement("div"); wrap.className="pri-wrap";
  const pool=document.createElement("div"); pool.className="pri-pool";
  const unassigned=items.filter(t=>!QUADS.some(q=>q.key===pr[t.uuid]));
  pool.innerHTML=`<div class="col-head"><span>Unsorted</span><span>${unassigned.length}</span></div>`;
  const pc=document.createElement("div"); pc.className="col-cards";
  if(!unassigned.length) pc.innerHTML=`<div class="empty" style="padding:16px 6px">All sorted 🎉</div>`;
  unassigned.forEach(t=>pc.appendChild(priCardEl(t))); pool.appendChild(pc); dropZone(pool,null,items); wrap.appendChild(pool);
  const mx=document.createElement("div"); mx.className="matrix";
  for(const q of QUADS){
    const quad=document.createElement("div"); quad.className="quad "+q.cls;
    quad.innerHTML=`<div class="quad-head"><div class="qt">${q.title}</div><div class="qs">${q.sub}</div></div>`;
    const cards=document.createElement("div"); cards.className="cards";
    items.filter(t=>pr[t.uuid]===q.key).forEach(t=>cards.appendChild(priCardEl(t)));
    quad.appendChild(cards); dropZone(quad,q.key,items); mx.appendChild(quad);
  }
  wrap.appendChild(mx); c.appendChild(wrap);
}
function priCardEl(t){
  const el=document.createElement("div"); el.className="pcard"; el.draggable=true;
  el.onclick=t._proj?()=>go("#l/"+encodeURIComponent(t.uuid)):()=>openEdit(t.uuid);
  el.addEventListener("dragstart",e=>{ e.dataTransfer.setData("text/id",t.uuid); el.classList.add("dragging"); });
  el.addEventListener("dragend",()=>el.classList.remove("dragging"));
  // Projects open on click and have no checkbox; to-dos get a complete box like the list rows.
  const box=t._proj?"":`<span class="box" title="Complete" style="cursor:pointer"></span>`;
  el.innerHTML=`<div style="display:flex;align-items:center;gap:8px">${box}<div class="pt">${esc(t.title||"(untitled)")}</div></div>`+
    (t._proj?`<div class="psub">Project</div>`:(t.project_title?`<div class="psub">${esc(t.project_title)}</div>`:""));
  if(!t._proj){ const b=el.querySelector(".box");
    b.onclick=(e)=>{ e.stopPropagation(); applyStatus(t.uuid,"completed").then(ok=>{ if(ok) el.remove(); }); }; }
  return el;
}
function dropZone(elm,quad,items){
  elm.addEventListener("dragover",e=>{ e.preventDefault(); elm.classList.add("drop"); });
  elm.addEventListener("dragleave",()=>elm.classList.remove("drop"));
  elm.addEventListener("drop",e=>{ e.preventDefault(); elm.classList.remove("drop");
    const id=e.dataTransfer.getData("text/id"); if(!id) return;
    CONFIG.priority=CONFIG.priority||{}; if(quad) CONFIG.priority[id]=quad; else delete CONFIG.priority[id];
    saveConfig().then(()=>renderMatrix(items));
  });
}

// --- priority levels (P1–P4 over Today; a task's level = its Things tags) ---
// Unlike the Eisenhower matrix (a per-uuid browser overlay you drag), a task's
// level is DERIVED from its real Things tags via the configurable priority_levels
// map. Dragging a card writes the level's canonical tag back to Things (token
// required); without a token the view is read-only — it just shows what's tagged.
function plevels(){
  // Always render four bands. Fill label/tags from config; default labels P1..P4.
  const cfg=(CONFIG.priority_levels||[]).slice(0,4);
  const out=[];
  for(let i=0;i<4;i++){ const e=cfg[i]||{}; out.push({label:(e.label||("P"+(i+1))), tags:(e.tags||[]).slice(), cls:"lvl-"+(i+1)}); }
  return out;
}
function levelTagSet(){ const s=new Set(); for(const l of plevels()) for(const t of l.tags) s.add(t); return s; }
function levelOf(item){ const tags=item.tags||[]; const L=plevels();
  for(let i=0;i<L.length;i++){ if(L[i].tags.some(t=>tags.includes(t))) return i; } return -1; }
async function renderLevels(){
  MODE="levels"; CUR_BOARD=null; SEL=null; setActive("levels");
  $(".main").classList.add("fill"); $("#board-gear").style.display="none"; $("#organize-btn").style.display="none";
  $("#levels-gear").style.display="flex";
  $("#filterbar").classList.remove("show"); $("#viewtog").classList.remove("show");
  $("#head-ico").innerHTML=SVG.levels; $("#head-title").textContent="Priority Levels"; setHeadEditable(null);
  const c=$("#content"); c.innerHTML=`<div class="empty">loading…</div>`;
  const data=await getJSON("/api/items?id=today");
  LIST_ITEMS=data.ok?data.items:[]; LIST_KIND="builtin"; renderLevelBands();
}
function renderLevelBands(){
  const c=$("#content"); c.innerHTML="";
  const L=plevels(); const anyMapped=L.some(l=>l.tags.length);
  const wrap=document.createElement("div"); wrap.className="pri-wrap";
  const pool=document.createElement("div"); pool.className="pri-pool";
  const unsorted=LIST_ITEMS.filter(t=>levelOf(t)<0);
  pool.innerHTML=`<div class="col-head"><span>Unsorted</span><span>${unsorted.length}</span></div>`;
  const pc=document.createElement("div"); pc.className="col-cards";
  if(!anyMapped) pc.innerHTML=`<div class="lvl-mapnote">No tags mapped yet. Click ⚙ to map your Things tags to P1–P4.</div>`;
  else if(!unsorted.length) pc.innerHTML=`<div class="empty" style="padding:16px 6px">All ranked 🎉</div>`;
  unsorted.forEach(t=>pc.appendChild(priCardEl(t))); pool.appendChild(pc); levelDrop(pool,-1); wrap.appendChild(pool);
  const bands=document.createElement("div"); bands.className="levels";
  L.forEach((lv,i)=>{
    const items=LIST_ITEMS.filter(t=>levelOf(t)===i);
    const band=document.createElement("div"); band.className="lvl "+lv.cls;
    const sub=lv.tags.length?lv.tags.map(esc).join(", "):"unmapped";
    band.innerHTML=`<div class="lvl-head"><span class="lt">${esc(lv.label)}</span><span class="ls">${sub}</span><span class="lc">${items.length}</span></div>`;
    const cards=document.createElement("div"); cards.className="cards";
    items.forEach(t=>cards.appendChild(priCardEl(t)));
    band.appendChild(cards); levelDrop(band,i); bands.appendChild(band);
  });
  wrap.appendChild(bands); c.appendChild(wrap);
}
function levelDrop(elm,levelIdx){
  elm.addEventListener("dragover",e=>{ e.preventDefault(); elm.classList.add("drop"); });
  elm.addEventListener("dragleave",()=>elm.classList.remove("drop"));
  elm.addEventListener("drop",async e=>{ e.preventDefault(); elm.classList.remove("drop");
    const id=e.dataTransfer.getData("text/id"); if(id) await assignLevel(id, levelIdx); });
}
// Re-tag in Things: strip every level tag the task carries, then add the target
// level's canonical tag (tags[0]). We send the full replacement set so the old
// level tag is removed in the same write. Token required; falls back to read-only.
async function assignLevel(uuid, levelIdx){
  if(!AUTH){ alert("Set THINGS_AUTH_TOKEN to rank tasks (the view is read-only without it)."); return; }
  const it=LIST_ITEMS.find(t=>t.uuid===uuid); if(!it) return;
  const L=plevels(), levelTags=levelTagSet();
  let tags=(it.tags||[]).filter(t=>!levelTags.has(t));
  if(levelIdx>=0){ const canon=L[levelIdx].tags[0];
    if(!canon){ alert("Map a tag to "+L[levelIdx].label+" first (⚙)."); return; }
    tags.push(canon); }
  const r=await postJSON("/api/update", {id:uuid, tags});
  if(!r.ok){ alert("Update failed: "+(r.error||"")); return; }
  it.tags=tags; renderLevelBands(); loadSidebar();
}
function openLevelMap(){
  const L=plevels(), rows=$("#levelmap-rows"); rows.innerHTML="";
  L.forEach((lv,i)=>{ const r=document.createElement("div"); r.className="lvl-tagrow";
    r.innerHTML=`<span class="lbl lvl-${i+1}">${esc(lv.label)}</span><input data-i="${i}" value="${esc(lv.tags.join(", "))}" placeholder="tag, tag">`;
    rows.appendChild(r); });
  const known=[...new Set((LIST_ITEMS||[]).flatMap(t=>t.tags||[]))];
  $("#levelmap-known").textContent=known.length?known.join(", "):"(none seen in Today yet)";
  openOverlay("levelmap-overlay");
}
async function saveLevelMap(){
  const rows=[...document.querySelectorAll("#levelmap-rows input")];
  const pl=rows.map((inp,i)=>({label:"P"+(i+1), tags:inp.value.split(",").map(s=>s.trim()).filter(Boolean)}));
  const r=await postJSON("/api/config", {priority_levels:pl});
  if(r.ok) CONFIG=r.config;
  closeOverlay("levelmap-overlay");
  if(MODE==="levels") renderLevelBands();
}

// --- timeline (day) view; blocks are a dashboard-only overlay, never written to Things ---
const TL_START=6, TL_END=23, TL_H=44;   // 6am–11pm, 44px per hour
let TL_DUR=30;                            // default block length (minutes)
function todayStr(){ const d=new Date(); return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0"); }
async function saveTimeblocks(){
  const r=await postJSON("/api/config", {timeblocks:CONFIG.timeblocks});
  if(r.ok) CONFIG=r.config;
}
function renderTimeline(items){
  const c=$("#content"); c.innerHTML=""; CONFIG.timeblocks=CONFIG.timeblocks||{};
  const day=todayStr();
  const wrap=document.createElement("div"); wrap.className="tl-wrap";
  // --- pool of unscheduled tasks (also a drop target to unschedule) ---
  const pool=document.createElement("div"); pool.className="tl-pool";
  const unscheduled=items.filter(t=>!(CONFIG.timeblocks[t.uuid] && CONFIG.timeblocks[t.uuid].date===day));
  pool.innerHTML=`<div class="col-head"><span>Unscheduled</span><span>${unscheduled.length}</span></div>`+
    `<div class="tl-durbar">New block <span class="durtog"></span> min</div>`;
  const pc=document.createElement("div"); pc.className="col-cards";
  if(!unscheduled.length) pc.innerHTML=`<div class="empty" style="padding:14px 6px">All slotted 🎉</div>`;
  unscheduled.forEach(t=>pc.appendChild(priCardEl(t))); pool.appendChild(pc);
  pool.addEventListener("dragover",e=>{ e.preventDefault(); pool.classList.add("drop"); });
  pool.addEventListener("dragleave",()=>pool.classList.remove("drop"));
  pool.addEventListener("drop",e=>{ e.preventDefault(); pool.classList.remove("drop");
    const id=e.dataTransfer.getData("text/id"); if(id && CONFIG.timeblocks[id]){ delete CONFIG.timeblocks[id]; saveTimeblocks().then(()=>renderTimeline(items)); } });
  wrap.appendChild(pool);
  [15,30,60].forEach(m=>{ const b=document.createElement("button"); b.className="vt"+(TL_DUR===m?" on":""); b.textContent=m; b.onclick=()=>{ TL_DUR=m; renderTimeline(items); }; pool.querySelector(".durtog").appendChild(b); });
  // --- the day grid ---
  const cal=document.createElement("div"); cal.className="tl-cal";
  const grid=document.createElement("div"); grid.className="tl-grid"; grid.style.height=((TL_END-TL_START)*TL_H)+"px";
  for(let h=TL_START; h<=TL_END; h++){
    const top=(h-TL_START)*TL_H;
    const line=document.createElement("div"); line.className="tl-hour"; line.style.top=top+"px"; grid.appendChild(line);
    const lab=document.createElement("div"); lab.className="tl-hlabel"; lab.style.top=top+"px"; lab.textContent=(h%12||12)+(h<12?"a":"p"); grid.appendChild(lab);
  }
  items.forEach(t=>{
    const b=CONFIG.timeblocks[t.uuid]; if(!b || b.date!==day) return;
    const [hh,mm]=b.start.split(":").map(Number); const startMin=hh*60+(mm||0);
    const el=document.createElement("div"); el.className="tl-block"; el.draggable=true;
    el.style.top=(((startMin-TL_START*60)/60)*TL_H)+"px"; el.style.height=Math.max(18,(b.mins/60)*TL_H-2)+"px";
    el.innerHTML=`<div class="bt">${esc(t.title||"(untitled)")}</div><div class="bsub">${b.start} · ${b.mins}m</div>`;
    el.onclick=()=>openEdit(t.uuid);
    el.addEventListener("dragstart",e=>{ e.dataTransfer.setData("text/id",t.uuid); el.classList.add("dragging"); });
    el.addEventListener("dragend",()=>el.classList.remove("dragging"));
    grid.appendChild(el);
  });
  grid.addEventListener("dragover",e=>e.preventDefault());
  grid.addEventListener("drop",e=>{
    e.preventDefault(); const id=e.dataTransfer.getData("text/id"); if(!id) return;
    const r=grid.getBoundingClientRect();
    let minutes=TL_START*60 + ((e.clientY-r.top)/TL_H)*60;
    minutes=Math.round(minutes/15)*15;
    minutes=Math.max(TL_START*60, Math.min(minutes, TL_END*60-15));
    const hh=String(Math.floor(minutes/60)).padStart(2,"0"), mm=String(minutes%60).padStart(2,"0");
    const ex=CONFIG.timeblocks[id];
    CONFIG.timeblocks[id]={date:day, start:hh+":"+mm, mins: ex?ex.mins:TL_DUR};
    saveTimeblocks().then(()=>renderTimeline(items));
  });
  cal.appendChild(grid); wrap.appendChild(cal); c.appendChild(wrap);
}

// --- board create / settings (auto-save) ---
async function newBoard(){
  const b={id:uid(),name:"New Board",columns:[...DEFAULT_COLUMNS],include_areas:[],include_projects:[],placements:{}};
  CONFIG.boards.push(b); await saveConfig(); renderSidebar(); CUR_BOARD=b.id; go("#b/"+encodeURIComponent(b.id));
  setTimeout(openBoardSettings,80);
}
function openBoardSettings(){
  const b=CONFIG.boards.find(x=>x.id===CUR_BOARD); if(!b) return;
  $("#b-name").value=b.name;
  const ce=$("#cols-edit"); ce.innerHTML=""; (b.columns||[]).forEach(c=>ce.appendChild(colInput(c)));
  const inc=$("#includes"); inc.innerHTML="";
  const aSet=new Set(b.include_areas||[]), pSet=new Set(b.include_projects||[]);
  for(const a of (SIDEBAR.areas||[])){
    const ah=document.createElement("div"); ah.className="area-pick";
    ah.innerHTML=`<label class="pick"><input type="checkbox" data-area="${a.uuid}" ${aSet.has(a.uuid)?"checked":""} onchange="persistSettings()"> ${esc(a.title)} <span style="color:var(--muted);font-weight:400">(entire area)</span></label>`;
    inc.appendChild(ah);
    for(const p of a.projects){
      const pe=document.createElement("div"); pe.className="proj-pick";
      pe.innerHTML=`<label class="pick"><input type="checkbox" data-project="${p.uuid}" ${pSet.has(p.uuid)?"checked":""} onchange="persistSettings()"> ${esc(p.title)}</label>`;
      inc.appendChild(pe);
    }
  }
  openOverlay("settings-overlay");
}
function colInput(val){
  const d=document.createElement("div"); d.className="col-edit"; d.draggable=true;
  d.innerHTML=`<span class="drag" title="Drag to reorder">⠿</span>`+
    `<input value="${esc(val)}" onchange="persistSettings()">`+
    `<button class="btn ghost" title="Remove" onclick="this.parentElement.remove(); persistSettings()">✕</button>`;
  d.addEventListener("dragstart",e=>{ d.classList.add("dragging"); e.dataTransfer.effectAllowed="move"; });
  d.addEventListener("dragend",()=>{ d.classList.remove("dragging"); persistSettings(); });  // persist new order
  d.addEventListener("dragover",e=>{ e.preventDefault();
    const box=$("#cols-edit"), dragging=box.querySelector(".col-edit.dragging");
    if(!dragging || dragging===d) return;
    const r=d.getBoundingClientRect();
    box.insertBefore(dragging, (e.clientY > r.top + r.height/2) ? d.nextSibling : d);
  });
  return d;
}
function addCol(){ $("#cols-edit").appendChild(colInput("")); }
async function persistSettings(){
  const b=CONFIG.boards.find(x=>x.id===CUR_BOARD); if(!b) return;
  b.name=$("#b-name").value.trim()||"Untitled board";
  b.columns=[...document.querySelectorAll("#cols-edit input")].map(i=>i.value.trim()).filter(Boolean);
  b.include_areas=[...document.querySelectorAll("#includes input[data-area]:checked")].map(i=>i.dataset.area);
  b.include_projects=[...document.querySelectorAll("#includes input[data-project]:checked")].map(i=>i.dataset.project);
  await saveConfig(); renderSidebar();
  if(MODE==="board"&&CUR_BOARD===b.id) renderBoard(b.id);   // refresh behind the modal
}
async function deleteBoard(){
  if(!confirm("Delete this board? (Your projects, tasks and tags in Things are untouched.)")) return;
  CONFIG.boards=CONFIG.boards.filter(x=>x.id!==CUR_BOARD); await saveConfig();
  closeOverlay("settings-overlay"); renderSidebar(); go("#l/today");
}

// --- edit dialog (Things-style card; saves on close only if changed) ---
let EDIT_ORIG=null, WHEN_SEED=null, EDIT_NEW=false, EDIT_KIND="todo", PENDING_ATTACH=[];
const WHEN_OPTS=[["today","Today"],["evening","This Evening"],["tomorrow","Tomorrow"],["anytime","Anytime"],["someday","Someday"]];
function autoGrow(el){ el.style.height="auto"; el.style.height=el.scrollHeight+"px"; }
function cachedItem(uuid){ return (LIST_ITEMS||[]).find(x=>x.uuid===uuid) || (TODAY_CACHE||[]).find(x=>x.uuid===uuid) || null; }
function scheduleLabel(ci){
  const today=new Date().toISOString().slice(0,10);
  if(ci.start_date) return ci.start_date===today?"Today":ci.start_date;
  if(ci.start==="Anytime") return "Anytime";
  if(ci.start==="Someday") return "Someday";
  return null;
}
function currentWhenLabel(){
  const w=$("#f-when").value.trim();
  if(w){ const o=WHEN_OPTS.find(x=>x[0]===w); return o?o[1]:w; }
  return WHEN_SEED;
}
function buildWhenChips(){
  const w=$("#when-chips"); w.innerHTML=""; const cur=$("#f-when").value.trim();
  WHEN_OPTS.forEach(([val,lbl])=>{
    const c=document.createElement("div"); c.className="chip"+(cur===val?" active":"");
    c.textContent=lbl; c.onclick=()=>{ $("#f-when").value=(cur===val?"":val); buildWhenChips(); updatePills(); };
    w.appendChild(c);
  });
}
function updatePills(){
  const box=$("#ec-pills"); if(!box) return; box.innerHTML="";
  const wl=currentWhenLabel();
  const wp=document.createElement("span"); wp.className="ec-pill when";
  wp.innerHTML=(wl==="Today"?SVG.today:"")+"<span>"+esc(wl||"When")+"</span>";
  wp.onclick=()=>toggleEditor("ed-when",$("#tool-when")); box.appendChild(wp);
  const dl=$("#f-deadline").value.trim();
  if(dl){ const d=document.createElement("span"); d.className="ec-pill dl"; d.innerHTML="⚑ <span>"+esc(dl)+"</span>";
    d.onclick=()=>toggleEditor("ed-deadline",$("#tool-deadline")); box.appendChild(d); }
  $("#f-tags").value.split(",").map(s=>s.trim()).filter(Boolean).forEach(t=>{
    const p=document.createElement("span"); p.className="ec-pill"; p.textContent=t;
    p.onclick=()=>toggleEditor("ed-tags",$("#tool-tags")); box.appendChild(p);
  });
}
function toggleEditor(id, tool){
  const ed=$("#"+id), show=!ed.classList.contains("show");
  ["ed-when","ed-deadline","ed-tags"].forEach(x=>$("#"+x).classList.remove("show"));
  ["tool-when","tool-deadline","tool-tags"].forEach(x=>$("#"+x).classList.remove("on"));
  if(show){ ed.classList.add("show"); if(tool) tool.classList.add("on");
    const inp=ed.querySelector("input"); if(inp&&!inp.disabled) setTimeout(()=>inp.focus(),0); }
}
// --- create mode: the edit card, reused for a brand-new to-do/project ---
function openCreate(kind){
  EDIT_NEW=true; EDIT_ID=null; EDIT_KIND=kind||"todo"; clearPending();
  ["f-title","f-notes","f-when","f-deadline","f-tags"].forEach(id=>{ $("#"+id).value=""; $("#"+id).disabled=false; });
  $("#f-checklist").innerHTML="";
  $("#ec-box").style.display="none";                     // nothing to complete yet
  $("#ec-kind").style.display="inline-flex"; setEditKind(EDIT_KIND);
  document.querySelectorAll("#edit-overlay .ec-link").forEach(b=>b.style.display="none");  // hide Cancel-task / Open-in-Things
  $("#ec-add").style.display="inline-block";
  ["ed-when","ed-deadline","ed-tags"].forEach(id=>$("#"+id).classList.remove("show"));
  ["tool-when","tool-deadline","tool-tags"].forEach(id=>$("#"+id).classList.remove("on"));
  $("#edit-warn").style.display=AUTH?"none":"block";
  WHEN_SEED=null; EDIT_ORIG=null; buildWhenChips(); renderPendingAttach(); updatePills();
  autoGrow($("#f-title")); autoGrow($("#f-notes"));
  openOverlay("edit-overlay"); setTimeout(()=>$("#f-title").focus(),0);
}
function setEditKind(k){
  EDIT_KIND=k; document.querySelectorAll("#ec-kind .vt").forEach(b=>b.classList.toggle("on", b.dataset.kind===k));
  let w;
  if(k==="project") w=(SEL&&SEL.kind==="area")?("in area: "+SEL.title):"top level";
  else w=(SEL&&(SEL.kind==="project"||SEL.kind==="area"))?("in: "+SEL.title):"to Inbox";
  const e=$("#ec-where"); e.textContent="→ "+w; e.style.display="inline";
}
// Staged images live only in the browser until the item exists (it has no UUID yet).
function stageAttach(file){
  if(!file || !/^image\\//.test(file.type)){ if(file) alert("Only images can be attached."); return; }
  PENDING_ATTACH.push({file, url:URL.createObjectURL(file), name:file.name||"image"}); renderPendingAttach();
}
function renderPendingAttach(){
  const box=$("#ec-attach"); if(!box) return; box.innerHTML="";
  PENDING_ATTACH.forEach((p,i)=>{ const d=document.createElement("div"); d.className="att";
    d.innerHTML=`<img src="${p.url}" alt="${esc(p.name)}">`+
      `<span class="att-x" title="Remove" onclick="unstageAttach(${i})">✕</span>`; box.appendChild(d); });
}
function unstageAttach(i){ const p=PENDING_ATTACH[i]; if(p) URL.revokeObjectURL(p.url); PENDING_ATTACH.splice(i,1); renderPendingAttach(); }
function clearPending(){ PENDING_ATTACH.forEach(p=>URL.revokeObjectURL(p.url)); PENDING_ATTACH=[]; }
let CREATING=false;   // re-entry guard: keying an image to its new task can take a few seconds
async function createFromCard(){
  if(CREATING) return;   // ignore the impatient second click that would create a duplicate
  let title=$("#f-title").value.trim(); if(!title){ $("#f-title").focus(); return; }
  let when=$("#f-when").value.trim(); const deadline=$("#f-deadline").value.trim();
  let tags=$("#f-tags").value.split(",").map(s=>s.trim()).filter(Boolean);
  if(EDIT_KIND==="todo"){ const p=parseNL(title); title=p.title; if(!when&&p.when) when=p.when; p.tags.forEach(t=>{ if(!tags.includes(t)) tags.push(t); }); }
  const body={kind:EDIT_KIND, title}; const notes=$("#f-notes").value.trim(); if(notes) body.notes=notes;
  // Snapshot the staged images at submit time: the /api/add wait is async, and a
  // paste/remove/drop mid-flight would otherwise change what we attach.
  const staged=PENDING_ATTACH.slice();
  if(staged.length) body.resolve=true;   // server must poll for the new UUID so we can attach
  if(EDIT_KIND==="project"){ if(SEL&&SEL.kind==="area") body.area_id=SEL.id; }
  else { if(when) body.when=when; if(deadline) body.deadline=deadline; if(tags.length) body.tags=tags;
         if(SEL&&(SEL.kind==="project"||SEL.kind==="area")) body.list_id=SEL.id; }
  // Resolving + attaching an image can take a few seconds (Things commits the DB
  // async). Show progress and lock the button so the wait doesn't look like a dead click.
  const btn=$("#ec-add"); const label=btn.textContent;
  CREATING=true; btn.disabled=true; btn.textContent=staged.length?"Adding image…":"Adding…";
  try{
    const r=await postJSON("/api/add", body);
    if(!r.ok){ alert("Add failed: "+(r.error||"")); return; }
    if(staged.length){
      if(r.uuid){ for(const p of staged) await uploadAttachmentTo(r.uuid, p.file); }
      else alert("Created, but couldn't link the image automatically — open the task and attach it.");
    }
    clearPending(); closeOverlay("edit-overlay"); loadSidebar(); setTimeout(route,400);
  }catch(e){
    alert("Add failed: "+(e&&e.message||e));   // a thrown fetch used to fail silently → "nothing happens"
  }finally{
    CREATING=false; btn.disabled=false; btn.textContent=label;
  }
}
async function openEdit(uuid){
  EDIT_ID=uuid; EDIT_NEW=false; clearPending();
  $("#ec-kind").style.display="none"; $("#ec-box").style.display=""; $("#ec-add").style.display="none"; $("#ec-where").style.display="none";
  document.querySelectorAll("#edit-overlay .ec-link").forEach(b=>b.style.display="");
  const data=await getJSON("/api/item?id="+encodeURIComponent(uuid));
  if(!data.ok){ alert("Could not load task."); return; }
  const it=data.item;
  $("#f-title").value=it.title||""; $("#f-notes").value=it.notes||"";
  $("#f-when").value=""; $("#f-deadline").value=it.deadline||""; $("#f-tags").value=(it.tags||[]).join(", ");
  $("#f-checklist").innerHTML=(it.checklist||[]).length
    ? `<div class="ec-checks">`+it.checklist.map(c=>`<div class="ci ${c.status==="completed"?"done":""}">${c.status==="completed"?"☑":"☐"} ${esc(c.title)}</div>`).join("")+`</div>` : "";
  ["ed-when","ed-deadline","ed-tags"].forEach(id=>$("#"+id).classList.remove("show"));
  ["tool-when","tool-deadline","tool-tags"].forEach(id=>$("#"+id).classList.remove("on"));
  const ci=cachedItem(uuid); WHEN_SEED=ci?scheduleLabel(ci):null;
  buildWhenChips();
  const ro=!AUTH; $("#edit-warn").style.display=ro?"block":"none";
  ["f-title","f-notes","f-when","f-deadline","f-tags"].forEach(id=>$("#"+id).disabled=ro);
  $("#ec-box").style.pointerEvents=ro?"none":"";
  EDIT_ORIG={title:it.title||"", notes:it.notes||"", deadline:it.deadline||"", tags:(it.tags||[]).join(",")};
  renderAttachments(uuid);
  updatePills(); openOverlay("edit-overlay"); setTimeout(()=>{ autoGrow($("#f-title")); autoGrow($("#f-notes")); },0);
}
// --- Image attachments (Things has no images; stored as a browser overlay) ---
function renderAttachments(uuid){
  const box=$("#ec-attach"); if(!box) return; box.innerHTML="";
  const list=(CONFIG.attachments||{})[uuid]||[];
  for(const a of list){
    const url="/api/attachment?uuid="+encodeURIComponent(uuid)+"&id="+encodeURIComponent(a.id);
    const d=document.createElement("div"); d.className="att";
    d.innerHTML=`<img src="${url}" alt="${esc(a.name||"image")}" onclick="window.open('${url}','_blank')">`+
      `<span class="att-x" title="Remove" onclick="detachAttachment('${uuid}','${a.id}')">✕</span>`+
      (a.caption?`<div class="att-cap" title="${esc(a.caption)}">${esc(a.caption)}</div>`:``);
    box.appendChild(d);
  }
}
function onAttachPick(ev){ const fs=ev.target.files; if(fs) for(const f of fs){ EDIT_NEW?stageAttach(f):uploadAttachment(EDIT_ID,f); } ev.target.value=""; }
function uploadAttachmentTo(uuid, file){   // returns Promise<bool>; keys the image to a known uuid
  // MUST always resolve: createFromCard awaits this, and a never-settling Promise
  // would leave CREATING=true and the Add button stuck disabled until a reload.
  return new Promise(res=>{
    if(!uuid || !file || !/^image\\//.test(file.type)){ if(file&&!/^image\\//.test(file.type)) alert("Only images can be attached."); res(false); return; }
    const reader=new FileReader();
    reader.onerror=()=>{ alert("Couldn't read the image file."); res(false); };   // failed read no longer hangs
    reader.onload=async()=>{
      try{
        const r=await postJSON("/api/attach", {uuid, name:file.name||"image", mime:file.type, data:String(reader.result)});
        if(!r.ok){ alert("Attach failed: "+(r.error||"")); res(false); return; }
        (CONFIG.attachments=CONFIG.attachments||{})[uuid]=((CONFIG.attachments||{})[uuid]||[]).concat([r.attachment]); res(true);
      }catch(e){ alert("Attach failed: "+(e&&e.message||e)); res(false); }   // a thrown fetch used to hang the Promise
    };
    reader.readAsDataURL(file);
  });
}
function uploadAttachment(uuid, file){   // attach to the open existing task + refresh its row icon
  uploadAttachmentTo(uuid, file).then(ok=>{ if(ok){ renderAttachments(uuid); rerenderCurrent(); } });
}
async function detachAttachment(uuid, id){
  const r=await postJSON("/api/detach", {uuid, id});
  if(!r.ok){ alert("Remove failed."); return; }
  if(CONFIG.attachments&&CONFIG.attachments[uuid]) CONFIG.attachments[uuid]=CONFIG.attachments[uuid].filter(a=>a.id!==id);
  renderAttachments(uuid); rerenderCurrent();   // refresh the row's image icon live
}
function editDirty(){
  if(!EDIT_ORIG) return false;
  const tags=$("#f-tags").value.split(",").map(s=>s.trim()).filter(Boolean).join(",");
  return $("#f-title").value!==EDIT_ORIG.title || $("#f-notes").value!==EDIT_ORIG.notes
    || tags!==EDIT_ORIG.tags || $("#f-when").value.trim()!=="" || $("#f-deadline").value.trim()!==EDIT_ORIG.deadline;
}
async function closeEdit(){
  if(EDIT_NEW){ clearPending(); closeOverlay("edit-overlay"); return; }  // ✕/Esc discards a new card (use Add to create)
  if(AUTH && editDirty()){ await saveEdit(); }   // saveEdit closes + re-renders
  else closeOverlay("edit-overlay");
}
async function saveEdit(){
  const tags=$("#f-tags").value.split(",").map(s=>s.trim()).filter(Boolean);
  const body={id:EDIT_ID,title:$("#f-title").value,notes:$("#f-notes").value,tags};
  const when=$("#f-when").value.trim(); if(when) body.when=when;
  body.deadline=$("#f-deadline").value.trim(); await postUpdate(body);
}
// Completing/canceling keeps the item VISIBLE as done (check + strikethrough) until a
// full refresh logs it — like Things, instead of vanishing instantly.
async function applyStatus(uuid, field){
  if(!AUTH){ alert("Set THINGS_AUTH_TOKEN to check off tasks."); return false; }
  const body={id:uuid}; body[field]=true;
  const r=await postJSON("/api/update", body);
  if(!r.ok){ alert("Update failed: "+(r.error||"")); return false; }
  const it=(LIST_ITEMS||[]).find(x=>x.uuid===uuid); if(it) it.status=(field==="completed"?"completed":"canceled");
  loadSidebar(); return true;   // refresh counts; the item stays in LIST_ITEMS until next full fetch
}
function rerenderCurrent(){
  if(MODE==="levels") return renderLevelBands();
  if(MODE==="cards") return renderCards(LIST_ITEMS);
  if(MODE==="matrix"){ let items=LIST_ITEMS.slice();
    if(LIST_KIND==="area") items=areaProjects(SEL.id).map(p=>({uuid:p.uuid,title:p.title,progress:p.progress,_proj:true})).concat(items);
    return renderMatrix(items); }
  if(MODE==="list") return renderRows();
}
async function completeTask(){ if(await applyStatus(EDIT_ID,"completed")){ closeOverlay("edit-overlay"); rerenderCurrent(); } }
async function cancelTask(){ if(await applyStatus(EDIT_ID,"canceled")){ closeOverlay("edit-overlay"); rerenderCurrent(); } }
async function postUpdate(body){
  const r=await postJSON("/api/update", body);
  if(!r.ok){ alert("Update failed: "+(r.error||"")); return; }
  closeOverlay("edit-overlay"); setTimeout(route,350);   // re-render current view
}
function openInThings(){ if(EDIT_ID) window.location.href="things:///show?id="+encodeURIComponent(EDIT_ID); }

// auto-organize folder (spawns your agent, review before write)
async function startOrganize(folderId, workflow){
  folderId = folderId || (SEL && SEL.id); workflow = workflow || "organize";
  if(!folderId){ alert("Open a list first."); return; }
  const r=await postJSON("/api/organize", {folder_id:folderId, workflow});
  if(!r.ok){ alert("Organize: "+(r.error||"failed")); return; }
  openOverlay("organize-overlay");
  const meta=({organize:["✨ Organize folder","Cleaner titles, notes, and tags — review before anything is written."],
               triage:["📥 Triage Inbox","Proposed home, tags, and date per item — review before anything is written."],
               calm:["🧘 Calm Today","Keep the vital few as Today; defer the rest — review before anything is written."]})[workflow]||["✨ Organize","Review before anything is written."];
  $("#org-title").textContent=meta[0]; $("#org-sub").textContent=meta[1];
  $("#org-actions").style.display="none";
  $("#org-body").innerHTML=`<div class="empty">Running ${esc(r.agent||"agent")} on ${r.count} task(s)… (up to ~2 min, costs a little on your agent account)</div>`;
  pollOrganize(r.job_id, 0);
}
function pollOrganize(jobId, tries){
  if(tries>90){ $("#org-body").innerHTML=`<div class="err">Timed out waiting for the agent.</div>`; return; }
  fetch("/api/organize?job_id="+encodeURIComponent(jobId)).then(r=>r.json()).then(d=>{
    if(d.status==="running"){ setTimeout(()=>pollOrganize(jobId,tries+1),2000); return; }
    if(d.status==="unknown"){ $("#org-body").innerHTML=`<div class="err">Job was lost (server restarted). Try again.</div>`; return; }
    if(d.status==="error"){ $("#org-body").innerHTML=`<div class="err">${esc(d.error||"failed")}</div>`; return; }
    ORG_SUG=d.suggestions||[]; renderSuggestions();
  }).catch(e=>{ $("#org-body").innerHTML=`<div class="err">${esc(""+e)}</div>`; });
}
function renderSuggestions(){
  const body=$("#org-body"); body.innerHTML="";
  const changed=ORG_SUG.filter(s=>s.suggested_title||s.append_notes||(s.tags&&s.tags.length)||s.when||s.dest);
  if(!changed.length){ body.innerHTML=`<div class="empty">No suggestions — looks tidy. 🎉</div>`; $("#org-actions").style.display="none"; return; }
  for(const s of changed){
    const row=document.createElement("div"); row.className="org-row"; row.dataset.uuid=s.uuid;
    let h=`<div class="org-cur">${esc(s.title || LAST_ITEMS[s.uuid] || "(task)")}</div>`;
    if(s.suggested_title) h+=`<label class="org-line"><input type="checkbox" class="acc-title" checked data-val="${esc(s.suggested_title)}"> ✏️ ${esc(s.suggested_title)}</label>`;
    if(s.dest) h+=`<label class="org-line"><input type="checkbox" class="acc-dest" checked data-val="${esc(s.dest)}"> 📁 → ${esc(s.dest)}</label>`;
    if(s.when) h+=`<label class="org-line"><input type="checkbox" class="acc-when" checked data-val="${esc(s.when)}"> 📅 ${esc(s.when)}</label>`;
    if(s.append_notes) h+=`<label class="org-line"><input type="checkbox" class="acc-notes" checked data-val="${esc(s.append_notes)}"> 📝 ${esc(s.append_notes)}</label>`;
    if(s.tags&&s.tags.length) h+=`<label class="org-line"><input type="checkbox" class="acc-tags" checked data-val="${esc(JSON.stringify(s.tags))}"> 🏷 ${s.tags.map(t=>`<span class="pill">${esc(t)}</span>`).join(" ")}</label>`;
    if(s.reason) h+=`<div class="org-reason">${esc(s.reason)}</div>`;
    row.innerHTML=h; body.appendChild(row);
  }
  $("#org-actions").style.display="flex";
}
async function applyOrganize(){
  let n=0;
  for(const row of [...document.querySelectorAll("#org-body .org-row")]){
    const body={id:row.dataset.uuid};
    const t=row.querySelector(".acc-title"); if(t&&t.checked) body.title=t.dataset.val;
    const no=row.querySelector(".acc-notes"); if(no&&no.checked) body.append_notes=no.dataset.val;
    const tg=row.querySelector(".acc-tags"); if(tg&&tg.checked){ try{ body.add_tags=JSON.parse(tg.dataset.val); }catch(e){} }
    const wn=row.querySelector(".acc-when"); if(wn&&wn.checked) body.when=wn.dataset.val;
    const ds=row.querySelector(".acc-dest"); if(ds&&ds.checked){ const lid=resolveDestId(ds.dataset.val); if(lid) body.list_id=lid; }
    if(body.title||body.append_notes||body.add_tags||body.when||body.list_id){
      const r=await postJSON("/api/update", body);
      if(r.ok) n++;
    }
  }
  closeOverlay("organize-overlay");
  setTimeout(()=>{ if(MODE==="list") renderList(SEL); }, 400);
  alert(`Applied ${n} task update(s).`);
}

// preferences (editor + terminal app)
function openPrefs(){ const p=CONFIG.prefs||{}; $("#pf-editor").value=p.editor||""; $("#pf-terminal").value=p.terminal||""; openOverlay("prefs-overlay"); }
async function savePrefs(){
  const prefs={editor:$("#pf-editor").value.trim(), terminal:$("#pf-terminal").value.trim()};
  const r=await postJSON("/api/config", {prefs});
  if(r.ok) CONFIG=r.config;
  closeOverlay("prefs-overlay");
}

// --- quick add: natural-language parse helpers (used by the create card) ---
function weekdayDate(s){
  const map={sunday:0,sun:0,monday:1,mon:1,tuesday:2,tue:2,tues:2,wednesday:3,wed:3,thursday:4,thu:4,thurs:4,friday:5,fri:5,saturday:6,sat:6};
  if(!(s in map)) return null;
  const t=new Date(), tgt=map[s]; let d=(tgt-t.getDay()+7)%7; if(d===0) d=7;  // next, not today
  const x=new Date(t.getFullYear(),t.getMonth(),t.getDate()+d);
  return x.getFullYear()+"-"+String(x.getMonth()+1).padStart(2,"0")+"-"+String(x.getDate()).padStart(2,"0");
}
// strict trailing-token parse: #tags + one when-keyword/weekday/yyyy-mm-dd; the rest stays literal
function relDate(nRaw, unit){
  const n=(nRaw==="a"||nRaw==="an")?1:parseInt(nRaw,10);
  if(!isFinite(n)) return null;
  const d=new Date();
  if(/^day/.test(unit)) d.setDate(d.getDate()+n);
  else if(/^week/.test(unit)) d.setDate(d.getDate()+7*n);
  else if(/^month/.test(unit)) d.setMonth(d.getMonth()+n);
  else if(/^year/.test(unit)) d.setFullYear(d.getFullYear()+n);
  else return null;
  return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");
}
// Trailing relative phrase → {when, n} where n tokens are consumed from the end.
// Handles "in 4 weeks", "in a month", "next week/month/year".
function relWhen(words){
  const tail=k=>words.slice(words.length-k).join(" ").toLowerCase();
  let m;
  if(words.length>=3 && (m=tail(3).match(/^in (\\d+|a|an) (day|days|week|weeks|month|months|year|years)$/)))
    { const w=relDate(m[1],m[2]); if(w) return {when:w, n:3}; }
  if(words.length>=2 && (m=tail(2).match(/^next (week|month|year)$/)))
    { const w=relDate("1",m[1]); if(w) return {when:w, n:2}; }
  return null;
}
function parseNL(raw){
  const WHEN=new Set(["today","tomorrow","evening","anytime","someday"]);
  let words=raw.trim().split(/\\s+/); let when=null; const tags=[]; let changed=true;
  while(words.length>1 && changed){
    changed=false; const last=words[words.length-1], lc=last.toLowerCase();
    if(last.startsWith("#")&&last.length>1){ tags.unshift(last.slice(1)); words.pop(); changed=true; continue; }
    if(!when){
      const rel=relWhen(words);
      if(rel){ when=rel.when; words.splice(words.length-rel.n, rel.n); changed=true; continue; }
      if(WHEN.has(lc)){ when=lc; words.pop(); changed=true; continue; }
      else if(/^\\d{4}-\\d{2}-\\d{2}$/.test(last)){ when=last; words.pop(); changed=true; continue; }
      else { const wd=weekdayDate(lc); if(wd){ when=wd; words.pop(); changed=true; continue; } }
    }
  }
  return {title:words.join(" ").trim()||raw.trim(), when, tags};
}
function openOverlay(id){ $("#"+id).classList.add("show"); }
function closeOverlay(id){ $("#"+id).classList.remove("show"); }
document.querySelectorAll(".overlay").forEach(o=>o.addEventListener("click",e=>{ if(e.target===o){ if(o.id==="edit-overlay") closeEdit(); else o.classList.remove("show"); } }));
document.addEventListener("keydown",e=>{ if(e.key==="Escape") document.querySelectorAll(".overlay.show").forEach(o=>{ if(o.id==="edit-overlay") closeEdit(); else o.classList.remove("show"); }); });
// Drag-drop + paste an image straight onto the open edit card.
(function(){ const card=document.querySelector("#edit-overlay .editcard"); if(!card) return;
  const editOpen=()=>$("#edit-overlay").classList.contains("show") && (EDIT_ID||EDIT_NEW);
  const take=f=>{ if(!/^image\\//.test(f.type))return; EDIT_NEW?stageAttach(f):uploadAttachment(EDIT_ID,f); };
  card.addEventListener("dragover",e=>{ if(!editOpen())return; e.preventDefault(); card.classList.add("ec-drop"); });
  card.addEventListener("dragleave",e=>{ if(e.target===card) card.classList.remove("ec-drop"); });
  card.addEventListener("drop",e=>{ if(!editOpen())return; e.preventDefault(); card.classList.remove("ec-drop");
    for(const f of (e.dataTransfer.files||[])) take(f); });
  document.addEventListener("paste",e=>{ if(!editOpen())return;
    for(const it of (e.clipboardData&&e.clipboardData.items||[])){ if(it.type&&/^image\\//.test(it.type)){ const f=it.getAsFile(); if(f) take(f); } } });
})();

// --- inline header rename (boards + projects; areas can't — no URL-scheme area update) ---
function setHeadEditable(type, id){
  const h=$("#head-title");
  h.dataset.etype=type||""; h.dataset.eid=id||"";
  h.contentEditable = type?"true":"false";
  h.classList.toggle("editable", !!type);
  h.title = type ? "Click to rename" : "";
}
async function commitHeadRename(){
  const h=$("#head-title"); const type=h.dataset.etype, id=h.dataset.eid;
  const name=h.textContent.trim(), orig=(h.dataset.orig||"").trim();
  if(h.dataset.cancel){ h.dataset.cancel=""; h.textContent=orig; return; }
  if(!type) return;
  if(!name || name===orig){ h.textContent=orig||name; return; }
  if(type==="board"){
    const b=CONFIG.boards.find(x=>x.id===id);
    if(b){ b.name=name; await saveConfig(); renderSidebar(); }
    return;
  }
  if(type==="project"){
    const r=await postJSON("/api/rename", {id, title:name, kind:"project"});
    if(!r.ok){ alert("Rename failed: "+(r.error||"")); h.textContent=orig; return; }
    loadSidebar();  // reflect new name in the nav tree
  }
}
(()=>{ const h=$("#head-title"); if(!h) return;
  h.addEventListener("focus",()=>{ h.dataset.orig=h.textContent; });
  h.addEventListener("keydown",e=>{ if(e.key==="Enter"){ e.preventDefault(); h.blur(); }
    else if(e.key==="Escape"){ e.preventDefault(); h.dataset.cancel="1"; h.blur(); } });
  h.addEventListener("blur", commitHeadRename);
})();

function renderAbout(){
  MODE="about"; CUR_BOARD=null;
  document.querySelectorAll(".nav-item,.area-head,.project").forEach(n=>n.classList.remove("active"));
  const al=$("#about-link"); if(al) al.classList.add("active");
  $(".main").classList.remove("fill"); $("#board-gear").style.display="none"; $("#organize-btn").style.display="none";
  $("#viewtog").classList.remove("show"); $("#filterbar").classList.remove("show");
  setHeadEditable(null); $("#head-ico").innerHTML=SVG.info; $("#head-title").textContent="About";
  $("#content").innerHTML=ABOUT_HTML;
}

async function reschedule(id, when){
  if(!AUTH){ alert("Set THINGS_AUTH_TOKEN to reschedule by drag."); return; }
  const r=await postJSON("/api/update", {id, when});
  if(!r.ok){ alert("Reschedule failed: "+(r.error||"")); return; }
  loadSidebar(); setTimeout(route, 300);
}

// --- auto-refresh: poll the live view, but never interrupt the user ---
function canAutoRefresh(){
  if(document.hidden) return false;                       // background tab
  if(document.querySelector(".overlay.show")) return false; // editing / organizing / prefs
  if(document.querySelector(".dragging")) return false;     // mid drag
  if(document.activeElement===$("#head-title")) return false; // renaming the header
  if(MODE==="search"||MODE==="about"||CUR_FILTER) return false; // focused on a filter/search/about
  return MODE==="list"||MODE==="matrix"||MODE==="board"||MODE==="timeline";
}
function softRefresh(){
  const c=$("#content"); const top=c?c.scrollTop:0;
  loadSidebar(); route();
  setTimeout(()=>{ const cc=$("#content"); if(cc) cc.scrollTop=top; }, 280);  // keep scroll
}
document.addEventListener("visibilitychange",()=>{ if(!document.hidden && canAutoRefresh()) softRefresh(); });

(async()=>{ await loadConfig(); await loadSidebar(); route();
  setInterval(()=>{ if(canAutoRefresh()) softRefresh(); }, 25000); })();
</script>
</body>
</html>
"""
