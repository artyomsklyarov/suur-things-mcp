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
import secrets
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
import uuid as _uuid
from importlib.resources import files as _pkg_files
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.routing import Route

from . import __version__, reads
from . import config as boardcfg
from . import organize as organizer
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
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response

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
    # no-store so an edited dashboard always reloads fresh (without it the browser
    # serves a stale page while the API keeps returning live data — confusing
    # "old icons, new counts" symptom).
    # Bake in the running version so the page can auto-reload itself after an
    # upgrade+restart (the app-mode window otherwise restores a stale page).
    # Replace the *quoted* marker with a JSON-encoded string so the version can
    # never break out of the JS string literal, whatever it contains.
    nonce = secrets.token_urlsafe(16)
    html = (
        _index_html()
        .replace('"__SUUR_VERSION__"', json.dumps(__version__))
        .replace("__CSP_NONCE__", nonce)
    )
    # Defence in depth for the innerHTML-heavy UI: task titles/notes are
    # semi-attacker-controllable (Mail to Things, agent-created tasks), so a missed
    # esc() must not become script execution. script-src is nonce-only (no inline
    # on* attributes anywhere — see wireStatic() in index.html); styles keep
    # 'unsafe-inline' for the many style="" attributes (injected CSS is a nuisance,
    # not code execution). img-src allows the YouTube thumbnails and the blob:/data:
    # previews for staged attachments.
    csp = (
        "default-src 'self'; "
        f"script-src 'nonce-{nonce}'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob: https://img.youtube.com; "
        "connect-src 'self'; "
        "object-src 'none'; base-uri 'none'; form-action 'self'; "
        "frame-ancestors 'none'"
    )
    return HTMLResponse(html, headers={
        "Cache-Control": "no-store",
        "Content-Security-Policy": csp,
    })


async def _version(_request: Request) -> JSONResponse:
    """The running server version — the page polls this and reloads itself when it
    changes (after an upgrade), so an open window never silently runs stale code."""
    return JSONResponse({"ok": True, "version": __version__})


def _change_cursor() -> str:
    """Cheap change token: mtime+size of the Things DB and its -wal (Things runs
    WAL mode, so commits touch the -wal file, not main.sqlite) plus board.json
    (the overlays). The page's 25s poll compares this before reloading — a quiet
    system costs a few stat() calls instead of full sidebar+list table scans on
    every tick of every open tab."""
    parts = []
    db = reads._db_path()
    for path in (db, db + "-wal", str(boardcfg._path())):
        try:
            st = os.stat(path)
            parts.append(f"{st.st_mtime_ns}-{st.st_size}")
        except OSError:
            parts.append("x")
    return "|".join(parts)


async def _cursor(_request: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "cursor": _change_cursor()})


# These reads hit the Things SQLite DB (hundreds of ms — _sidebar scans ~1.3k
# projects). Run them off the event loop so they can't stall concurrent requests
# — most importantly the quick-add resolve poll, whose asyncio.sleep clock would
# otherwise stretch from ~1.8s to many seconds, making "Add" look dead.
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
            Route("/api/version", _version),
            Route("/api/cursor", _cursor),
            Route("/api/organize", _organize_get),
            Route("/api/organize", _organize_post, methods=["POST"]),
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


# --- launchd service (install/uninstall) -----------------------------------
# Productizes the "run the dashboard as a login service" setup: a KeepAlive
# LaunchAgent running `dashboard --no-open`, so the board is always live on
# :8765 without a terminal or a browser tab popping on every restart.

_SERVICE_LABEL = "io.suur.things-dashboard"


def _service_plist_path() -> str:
    return os.path.expanduser(f"~/Library/LaunchAgents/{_SERVICE_LABEL}.plist")


def _service_command() -> list[str]:
    """The command the service runs. Prefer `uvx` (a stable binary that resolves
    the latest installed release each start); fall back to the current
    interpreter, whose path may be an ephemeral uvx env — fine for uv tool /
    pipx / venv installs."""
    uvx = shutil.which("uvx")
    if uvx:
        return [uvx, "suur-things-mcp", "dashboard", "--no-open"]
    import sys

    return [sys.executable, "-m", "suur_things_mcp", "dashboard", "--no-open"]


def _service_plist(cmd: list[str]) -> str:
    log = os.path.expanduser("~/Library/Logs/suur-things-dashboard.log")
    args = "\n".join(f"    <string>{c}</string>" for c in cmd)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{_SERVICE_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
{args}
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
</dict>
</plist>
"""


def install_service() -> int:
    """Write + load the LaunchAgent. Returns a process exit code."""
    plist = _service_plist_path()
    # A live dashboard NOT started by our agent means some other supervisor
    # (e.g. a hand-rolled LaunchAgent) owns port 8765. Installing a second
    # KeepAlive service would make the two fight over the port forever.
    if _dashboard_alive(DEFAULT_PORT) and not os.path.exists(plist):
        print(
            f"A dashboard is already running on :{DEFAULT_PORT} but wasn't started by "
            f"this service ({_SERVICE_LABEL}).\nIf you manage it with your own "
            "launchd agent, keep using that — or unload it first, then re-run "
            "--install-service."
        )
        return 1
    uid = os.getuid()
    # Replace an existing installation cleanly (ignore bootout failures).
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{_SERVICE_LABEL}"],
                   capture_output=True, text=True)
    os.makedirs(os.path.dirname(plist), exist_ok=True)
    with open(plist, "w", encoding="utf-8") as f:
        f.write(_service_plist(_service_command()))
    r = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", plist],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"launchctl bootstrap failed: {r.stderr.strip() or r.stdout.strip()}")
        return 1
    print(f"Installed + started {_SERVICE_LABEL}")
    print(f"  plist : {plist}")
    print(f"  board : http://127.0.0.1:{DEFAULT_PORT}")
    print("  note  : for write access, keep your token in "
          "~/.config/suur-things-mcp/token (chmod 600) — the service reads it "
          "from there; no secret is stored in the plist.")
    return 0


def uninstall_service() -> int:
    plist = _service_plist_path()
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{_SERVICE_LABEL}"],
                   capture_output=True, text=True)
    if os.path.exists(plist):
        os.unlink(plist)
        print(f"Uninstalled {_SERVICE_LABEL} and removed {plist}")
    else:
        print(f"{_SERVICE_LABEL} was not installed (no plist at {plist})")
    return 0


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


# --- Frontend (single self-contained page, shipped as package data) --------

def _index_html() -> str:
    """The dashboard page from static/index.html, read per request so an edit is
    live on the next reload (no build step; a local read is microseconds). The
    file ships inside the wheel as package data."""
    return (_pkg_files(__package__) / "static" / "index.html").read_text("utf-8")
