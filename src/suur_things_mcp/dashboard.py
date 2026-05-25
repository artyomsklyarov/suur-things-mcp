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

import json
import os
import re
import shutil
import socket
import subprocess
import threading
from typing import Any
import urllib.request
from urllib.parse import urlparse

import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
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

_ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
_GITHUB_SLUG_RE = re.compile(r"^[\w.-]+/[\w.-]+$")


class _OriginGuard(BaseHTTPMiddleware):
    """Reject cross-site POSTs. 127.0.0.1 binding alone doesn't stop a webpage in
    your browser from POSTing to localhost (CSRF/DNS-rebind), and our POSTs can
    write config and launch local apps. Same-origin fetches from our own page pass.
    """

    async def dispatch(self, request: Request, call_next):
        if request.method == "POST":
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"ok": False, "error": "cross-site blocked"}, status_code=403)
            origin = request.headers.get("origin")
            if origin and urlparse(origin).hostname not in _ALLOWED_HOSTS:
                return JSONResponse({"ok": False, "error": "bad origin"}, status_code=403)
        return await call_next(request)

DEFAULT_PORT = 8765
_running: dict[str, Any] = {}


def _auth_token() -> str | None:
    return boardcfg.auth_token()


# --- Read endpoints -------------------------------------------------------

async def _index(_request: Request) -> HTMLResponse:
    # no-store so an edited dashboard always reloads fresh (the HTML is baked into
    # this module; without this the browser serves a stale page while the API
    # keeps returning live data — confusing "old icons, new counts" symptom).
    return HTMLResponse(INDEX_HTML, headers={"Cache-Control": "no-store"})


async def _state(_request: Request) -> JSONResponse:
    try:
        return JSONResponse({"ok": True, "board": reads.board()})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc), "board": {}})


async def _sidebar(_request: Request) -> JSONResponse:
    try:
        return JSONResponse(
            {"ok": True, "auth": bool(_auth_token()), "sidebar": reads.sidebar()}
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc), "sidebar": {}})


async def _items(request: Request) -> JSONResponse:
    list_id = request.query_params.get("id", "today")
    try:
        return JSONResponse({"ok": True, **reads.list_items(list_id)})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc), "items": []})


async def _item(request: Request) -> JSONResponse:
    detail = reads.item_detail(request.query_params.get("id", ""))
    return JSONResponse({"ok": detail is not None, "item": detail})


async def _search(request: Request) -> JSONResponse:
    q = (request.query_params.get("q") or "").strip()
    if len(q) < 2:
        return JSONResponse({"ok": True, "items": []})
    try:
        import things

        res = things.search(q) or []
        items = [reads._card(t) for t in res if t.get("type") == "to-do"][:60]
        return JSONResponse({"ok": True, "items": items})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc), "items": []})


# --- Boards + config ------------------------------------------------------

async def _board(request: Request) -> JSONResponse:
    board = boardcfg.get_board(request.query_params.get("id", ""))
    if board is None:
        return JSONResponse({"ok": False, "error": "board not found", "columns": []})
    try:
        cards = reads.board_cards(board)
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
                    r["github"] = _detect_github(path)
        cfg = boardcfg.set_item_repos(item_id, body.get("kind", "project"), repos)
        return JSONResponse({"ok": True, "config": cfg})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc)})


# --- Writes (task editing requires THINGS_AUTH_TOKEN) ----------------------

async def _update(request: Request) -> JSONResponse:
    token = _auth_token()
    if not token:
        return JSONResponse({"ok": False, "error": "THINGS_AUTH_TOKEN not set"})
    body = await request.json()
    if not body.get("id"):
        return JSONResponse({"ok": False, "error": "missing id"})
    params: dict[str, Any] = {"id": body["id"]}
    for key in ("title", "notes", "when", "deadline"):
        if body.get(key) is not None:
            params[key] = body[key]
    if body.get("tags") is not None:
        params["tags"] = ",".join(body["tags"])
    if body.get("append_notes"):
        params["append-notes"] = body["append_notes"]
    if body.get("add_tags"):
        params["add-tags"] = ",".join(body["add_tags"])
    if body.get("completed"):
        params["completed"] = True
    if body.get("canceled"):
        params["canceled"] = True
    try:
        execute("update", params, auth_token=token)
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
    return JSONResponse({"ok": True, "repos": out})


async def _rename(request: Request) -> JSONResponse:
    """Rename a project inline from the dashboard header. (Board renames are client-side
    config; areas can't be renamed — the Things URL Scheme has no area-update command.)"""
    body = await request.json()
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
        execute("update-project", {"id": item_id, "title": title}, auth_token=_auth_token())
        return JSONResponse({"ok": True})
    except ThingsURLError as exc:
        return JSONResponse({"ok": False, "error": str(exc)})


async def _open(request: Request) -> JSONResponse:
    """Open a linked repo in the editor or its GitHub page.

    Takes only an item_id + repo index + target; the path/url is looked up and
    validated server-side (never trusted from the request).
    """
    body = await request.json()
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
        subprocess.run(["open", f"https://github.com/{gh}"], check=False, timeout=5)
        return JSONResponse({"ok": True})
    path = entry.get("repo")
    if not path or not os.path.isdir(path):
        return JSONResponse({"ok": False, "error": "repo path not found on disk"})
    if target == "editor":
        editor = prefs.get("editor") or os.environ.get("SUUR_THINGS_EDITOR")
        cmd = [editor, path] if editor and shutil.which(editor) else ["open", path]
        subprocess.run(cmd, check=False, timeout=5)
        return JSONResponse({"ok": True})
    if target == "terminal":
        app = prefs.get("terminal") or os.environ.get("SUUR_THINGS_TERMINAL") or "Terminal"
        subprocess.run(["open", "-a", app, path], check=False, timeout=5)
        return JSONResponse({"ok": True})
    return JSONResponse({"ok": False, "error": "bad target"})


def _evict_jobs() -> None:
    now = time.time()
    for jid in [k for k, v in _ORGANIZE_JOBS.items()
                if v.get("status") != "running" and now - v.get("ts", now) > _ORGANIZE_TTL]:
        _ORGANIZE_JOBS.pop(jid, None)


async def _organize_post(request: Request) -> JSONResponse:
    """Start a background 'organize folder' agent run. Returns a job_id to poll."""
    if not _auth_token():
        return JSONResponse({"ok": False, "error": "THINGS_AUTH_TOKEN not set (needed to apply changes)"})
    body = await request.json()
    folder_id = str(body.get("folder_id") or "")
    if not folder_id:
        return JSONResponse({"ok": False, "error": "missing folder_id"})
    agent = organizer.pick_agent(boardcfg.prefs())
    if not agent:
        return JSONResponse({"ok": False, "error": "no agent CLI found — install Claude Code or Codex"})

    _evict_jobs()
    for jid, job in _ORGANIZE_JOBS.items():  # dedupe: same folder already running
        if job.get("status") == "running" and job.get("folder_id") == folder_id:
            return JSONResponse({"ok": True, "job_id": jid})
    if any(j.get("status") == "running" for j in _ORGANIZE_JOBS.values()):  # global cap of 1
        return JSONResponse({"ok": False, "error": "another organize job is already running"})

    try:
        cards = reads.list_items(folder_id).get("items", [])[: organizer.MAX_TASKS]
        tasks = []
        for c in cards:
            full = reads.get(c["uuid"]) or {}
            tasks.append({"uuid": c["uuid"], "title": c.get("title"),
                          "notes": full.get("notes"), "tags": full.get("tags") or c.get("tags")})
        if not tasks:
            return JSONResponse({"ok": False, "error": "no open tasks in this folder"})
        obj = reads.get(folder_id)
        title = (obj.get("title") if obj else None) or folder_id
        existing_tags = [t.get("title") for t in reads.tags() if t.get("title")]
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc)})

    model = boardcfg.prefs().get("agent_model") or organizer.DEFAULT_MODEL
    job_id = _uuid.uuid4().hex[:8]
    _ORGANIZE_JOBS[job_id] = {"status": "running", "folder_id": folder_id, "ts": time.time(),
                              "suggestions": None, "error": None, "count": len(tasks)}

    def _work() -> None:
        try:
            sug = organizer.organize(title, tasks, existing_tags, agent, model)
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


def create_app() -> Starlette:
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
            Route("/api/open", _open, methods=["POST"]),
        ],
        middleware=[Middleware(_OriginGuard)],
    )


# --- Server lifecycle -----------------------------------------------------

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


def ensure_running(open_browser: bool = True) -> str:
    if _running.get("url"):
        return _running["url"]
    if _dashboard_alive(DEFAULT_PORT):  # reuse an instance already on the stable port
        url = f"http://127.0.0.1:{DEFAULT_PORT}"
        _running.update(url=url, port=DEFAULT_PORT)
        if open_browser:
            try:
                subprocess.run(["open", url], check=False, timeout=5)
            except Exception:  # noqa: BLE001
                pass
        return url
    port = _pick_port()
    config = uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True, name="things-dashboard")
    thread.start()
    url = f"http://127.0.0.1:{port}"
    _running.update(url=url, port=port, thread=thread, server=server)
    if open_browser:
        try:
            subprocess.run(["open", url], check=False, timeout=5)
        except Exception:  # noqa: BLE001
            pass
    return url


def serve_foreground(port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
    if _dashboard_alive(port):  # already running on the stable port — don't duplicate
        url = f"http://127.0.0.1:{port}"
        print(f"Things dashboard already running → {url}")
        if open_browser:
            try:
                subprocess.run(["open", url], check=False, timeout=5)
            except Exception:  # noqa: BLE001
                pass
        return
    chosen = _pick_port(port)
    if chosen != port:
        print(f"Port {port} is busy (not our dashboard); using {chosen} instead.")
    url = f"http://127.0.0.1:{chosen}"
    print(f"Things dashboard → {url}  (Ctrl-C to stop)")
    if open_browser:
        try:
            subprocess.run(["open", url], check=False, timeout=5)
        except Exception:  # noqa: BLE001
            pass
    uvicorn.run(create_app(), host="127.0.0.1", port=chosen, log_level="warning")


# --- Frontend (self-contained, no external deps) --------------------------

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SUUR Things</title>
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

  /* Quick search */
  .search { margin-left:20px; width:240px; max-width:38vw; font:inherit; font-size:13px; padding:6px 11px;
    border-radius:8px; border:1px solid var(--divider); background:var(--side-bg); color:var(--text); }
  .search::placeholder { color:var(--muted); } .search:focus { outline:none; border-color:var(--accent); }

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

  .org-row { border:1px solid var(--divider); border-radius:9px; padding:10px 12px; margin:8px 0; }
  .org-cur { color:var(--muted); font-size:12px; text-decoration:line-through; margin-bottom:5px; }
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
  .card .crepos { margin-top:8px; display:flex; flex-wrap:wrap; gap:6px; align-items:center; }
  .card .cpulse { color:var(--muted); font-size:11px; margin-top:8px; }
  .card .repo { font-size:11px; color:var(--muted); border:1px solid var(--pill-border); border-radius:8px; padding:1px 3px 1px 8px; display:inline-flex; align-items:center; gap:1px; }
  .card .rb { border:0; background:transparent; cursor:pointer; color:var(--muted); font-size:12px; padding:0 4px; border-radius:5px; line-height:1.6; }
  .card .rb:hover { background:var(--row-hover); color:var(--text); }
  .card .rb.add { border:1px dashed var(--pill-border); border-radius:8px; padding:0 7px; }

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
  .area-pick { font-weight:600; margin:12px 0 4px; } .proj-pick { padding-left:18px; }
  .pick { display:flex; align-items:center; gap:8px; padding:3px 0; cursor:pointer; font-weight:400; }
  .repo-row { display:flex; gap:6px; margin:6px 0; align-items:center; }
  .repo-row .rr-label { flex:0 0 130px; } .repo-row .rr-path { flex:1; } .repo-row .rr-gh { flex:0 0 160px; }
</style>
</head>
<body>
<div class="topbar">
  <div class="brand">SUUR THINGS</div>
  <input id="q" class="search" placeholder="Search tasks…" autocomplete="off" oninput="onSearch()">
  <span class="grow"></span>
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
      <div class="viewtog" id="viewtog">
        <button class="vt" id="vt-list" onclick="setListView('list')">List</button>
        <button class="vt" id="vt-matrix" onclick="setListView('matrix')">Matrix</button>
        <button class="vt" id="vt-cards" onclick="setListView('cards')">Cards</button>
      </div>
      <button class="iconbtn" id="organize-btn" title="Auto-organize this folder with your agent" style="display:none" onclick="startOrganize()">✨</button>
      <button class="iconbtn" id="board-gear" title="Board settings" style="display:none" onclick="openBoardSettings()">⚙</button>
    </div>
    <div class="filterbar" id="filterbar"></div>
    <div id="content"></div>
  </main>
</div>

<div class="overlay" id="edit-overlay">
  <div class="editcard">
    <span class="ec-x" title="Close (saves changes)" onclick="closeEdit()">✕</span>
    <div class="ec-top">
      <span class="ec-box" id="ec-box" title="Complete" onclick="completeTask()"></span>
      <textarea class="ec-title" id="f-title" rows="1" placeholder="New To-Do" oninput="autoGrow(this)"></textarea>
    </div>
    <textarea class="ec-notes" id="f-notes" placeholder="Notes" oninput="autoGrow(this)"></textarea>
    <div class="ec-pills" id="ec-pills"></div>
    <div id="f-checklist"></div>
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
      <span class="spacer"></span>
      <button class="ec-link" onclick="cancelTask()">Cancel task</button>
      <button class="ec-link" onclick="openInThings()">Open in Things ↗</button>
    </div>
  </div>
</div>

<div class="overlay" id="organize-overlay">
  <div class="panel" style="width:640px">
    <h2>✨ Organize folder</h2><div class="sub">Your agent suggests improvements. Nothing is written until you Apply.</div>
    <div id="org-body"></div>
    <div class="btnrow" id="org-actions" style="display:none">
      <button class="btn primary" onclick="applyOrganize()">Apply selected</button>
      <span class="spacer"></span>
      <button class="btn ghost" onclick="closeOverlay('organize-overlay')">Close</button>
    </div>
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
let AUTH=false, SIDEBAR=null, CONFIG={boards:[],priority:{}};
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
function setHeadIcon(sel){
  const el=$("#head-ico");
  if(sel.kind==="builtin" && SVG[sel.id]){ el.innerHTML=SVG[sel.id]; return; }
  if(sel.kind==="project"){ const p=findProject(sel.id); el.innerHTML=p?ring(p.progress):""; return; }
  el.textContent="";  // areas show their name large, no glyph (matches Things)
}
function esc(s){ return String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
function linkify(s){ return esc(s).replace(/(https?:\\/\\/[^\\s]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>'); }
function uid(){ return Math.random().toString(36).slice(2,10); }

function applyTheme(t){ document.documentElement.setAttribute("data-theme",t); $("#theme").textContent=t==="dark"?"☀":"☾"; localStorage.setItem("things-theme",t); }
applyTheme(localStorage.getItem("things-theme") || (matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"));
$("#theme").onclick=()=>applyTheme(document.documentElement.getAttribute("data-theme")==="dark"?"light":"dark");

function ring(p){ const r=6,c=2*Math.PI*r,off=c*(1-p);
  if(p<=0) return `<svg class="ring" width="16" height="16" viewBox="0 0 16 16"><circle class="ring-bg" cx="8" cy="8" r="6"/></svg>`;
  return `<svg class="ring" width="16" height="16" viewBox="0 0 16 16"><circle class="ring-bg" cx="8" cy="8" r="6"/><circle class="ring-fg" cx="8" cy="8" r="6" stroke-dasharray="${c.toFixed(2)}" stroke-dashoffset="${off.toFixed(2)}" transform="rotate(-90 8 8)"/></svg>`; }

async function loadConfig(){ CONFIG=(await (await fetch("/api/config")).json()).config; }
// Save only the sections this client owns in this action, so a concurrent edit
// (CLI / another tab) to a different section is never clobbered.
async function saveConfig(){
  const r=await (await fetch("/api/config",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({boards:CONFIG.boards, priority:CONFIG.priority})})).json();
  if(r.ok) CONFIG=r.config;
}
async function saveItemRepos(itemId, kind, repos){
  const r=await (await fetch("/api/link",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({item_id:itemId, kind, repos})})).json();
  if(r.ok) CONFIG=r.config;
}

// --- navigation (hash-based, Back/Forward works) ---
function go(h){ if(location.hash===h) route(); else location.hash=h; }
function route(){
  const h=location.hash;
  if(h==="#about") return renderAbout();
  if(h==="#p") return renderPriority();
  if(h.startsWith("#b/")){ const id=decodeURIComponent(h.slice(3)); if(CONFIG.boards.find(b=>b.id===id)) return renderBoard(id); }
  if(h.startsWith("#l/")){ let rest=h.slice(3); let view="list";
    if(rest.endsWith("/m")){ view="matrix"; rest=rest.slice(0,-2); }
    else if(rest.endsWith("/c")){ view="cards"; rest=rest.slice(0,-2); }
    const sel=resolveList(decodeURIComponent(rest)); if(sel) return renderList(sel, view); }
  return go("#l/today");
}
window.addEventListener("hashchange", route);

// --- quick search (things.search over the whole DB) ---
let SEARCH_T=null;
function onSearch(){ clearTimeout(SEARCH_T); SEARCH_T=setTimeout(runSearch,220); }
async function runSearch(){
  const q=$("#q").value.trim();
  if(q.length<2){ if(MODE==="search") route(); return; }
  MODE="search"; CUR_BOARD=null;
  $("#viewtog").classList.remove("show"); $("#filterbar").classList.remove("show");
  $(".main").classList.remove("fill"); $("#board-gear").style.display="none"; $("#organize-btn").style.display="none";
  document.querySelectorAll(".nav-item,.area-head,.project").forEach(n=>n.classList.remove("active"));
  $("#head-ico").innerHTML=SVG.search; $("#head-title").textContent="Search"; setHeadEditable(null);
  const c=$("#content"); c.innerHTML=`<div class="empty">searching…</div>`;
  const data=await (await fetch("/api/search?q="+encodeURIComponent(q))).json();
  if(!data.ok){ c.innerHTML=`<div class="err">${esc(data.error||"error")}</div>`; return; }
  LIST_ITEMS=data.items; LAST_ITEMS={}; data.items.forEach(it=>LAST_ITEMS[it.uuid]=it.title);
  c.innerHTML="";
  if(!data.items.length){ c.innerHTML=`<div class="empty">No matches for “${esc(q)}”.</div>`; return; }
  data.items.forEach(it=>c.appendChild(rowEl(it)));
}

// --- sidebar ---
async function loadSidebar(){
  const data=await (await fetch("/api/sidebar")).json();
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
let LIST_ITEMS=[], LIST_KIND="", LIST_NOTES=null, CUR_FILTER=null;
async function renderList(sel, view="list"){
  const matrix=view==="matrix", cards=view==="cards";
  MODE=view; CUR_BOARD=null; SEL=sel;
  $("#board-gear").style.display="none"; setActive(sel.id);
  setHeadIcon(sel); $("#head-title").textContent=sel.title;
  setHeadEditable(sel.kind==="project"?"project":null, sel.id);
  $("#viewtog").classList.add("show");
  $("#vt-list").classList.toggle("on",view==="list"); $("#vt-matrix").classList.toggle("on",matrix); $("#vt-cards").classList.toggle("on",cards);
  $(".main").classList.toggle("fill", matrix);
  const c=$("#content"); $("#filterbar").classList.remove("show"); c.innerHTML=`<div class="empty">loading…</div>`;
  const data=await (await fetch("/api/items?id="+encodeURIComponent(sel.id))).json();
  if(!data.ok){ c.innerHTML=`<div class="err">${esc(data.error||"error")}</div>`; return; }
  LIST_ITEMS=data.items; LIST_KIND=data.kind; LIST_NOTES=data.notes||null; CUR_FILTER=null;
  LAST_ITEMS={}; LIST_ITEMS.forEach(it=>{ LAST_ITEMS[it.uuid]=it.title; });
  $("#organize-btn").style.display=(view==="list"&&(LIST_KIND==="project"||LIST_KIND==="area"||sel.id==="inbox"))?"flex":"none";
  if(matrix){
    let items=LIST_ITEMS.slice();
    if(LIST_KIND==="area") items=areaProjects(sel.id).map(p=>({uuid:p.uuid,title:p.title,progress:p.progress,_proj:true})).concat(items);
    renderMatrix(items);
  } else if(cards){ renderCards(LIST_ITEMS); }
  else { buildFilterBar(); renderRows(); }
}
function setListView(v){ if(SEL) go("#l/"+encodeURIComponent(SEL.id)+(v==="matrix"?"/m":v==="cards"?"/c":"")); }
function areaProjects(areaId){ const a=((SIDEBAR&&SIDEBAR.areas)||[]).find(x=>x.uuid===areaId); return a?a.projects:[]; }
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
  const projs=(LIST_KIND==="area"&&!CUR_FILTER)?areaProjects(SEL.id):[];
  if(projs.length){ const g=document.createElement("div"); g.className="projcards"; projs.forEach(p=>g.appendChild(projCardEl(p))); c.appendChild(g); }
  let items=LIST_ITEMS;
  if(CUR_FILTER) items=items.filter(it=>(it.tags||[]).includes(CUR_FILTER));
  if(!items.length){ if(!projs.length){ const e=document.createElement("div"); e.className="empty"; e.textContent="Nothing here."; c.appendChild(e); } return; }
  const key=LIST_KIND==="project"?"heading_title":"project_title";
  const groups=groupBy(items,key).sort((a,b)=>(a.key?1:0)-(b.key?1:0));
  for(const g of groups){ if(g.key){ const h=document.createElement("div"); h.className="grp-head"; h.textContent=g.key; c.appendChild(h);} for(const it of g.items) c.appendChild(rowEl(it)); }
}
function groupBy(items,key){ const g=[],idx={};
  for(const it of items){ const k=it[key]||"\\u0000"; if(!(k in idx)){idx[k]=g.length; g.push({key:it[key]||null,items:[]});} g[idx[k]].items.push(it);} return g; }
function metaHtml(it){ let m="";
  if(it.has_notes) m+=`<span class="note-ico">📄</span>`;
  (it.tags||[]).forEach(t=>m+=`<span class="pill">${esc(t)}</span>`);
  if(it.deadline){ const od=it.deadline<new Date().toISOString().slice(0,10); m+=`<span class="due">${od?'<span class="dot"></span>':"⚑"} ${it.deadline}</span>`; }
  return m; }
function rowEl(it){
  const done=it.status==="completed",cancel=it.status==="canceled";
  const row=document.createElement("div"); row.className="row"+(done||cancel?" is-done":""); row.onclick=()=>openEdit(it.uuid);
  row.draggable=true;  // drag onto a sidebar bucket (Today/Anytime/Someday) to reschedule
  row.addEventListener("dragstart",e=>{ e.dataTransfer.setData("text/id",it.uuid); row.classList.add("dragging"); });
  row.addEventListener("dragend",()=>row.classList.remove("dragging"));
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
  const data=await (await fetch("/api/board?id="+encodeURIComponent(id))).json();
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
  let repoHtml="";
  (card.repos||[]).forEach((r,i)=>{
    const lbl = r.label || (r.github? r.github.split("/")[1] : "repo");
    repoHtml += `<span class="repo">${esc(lbl)}`+
      `<button class="rb" title="Open in editor" onclick="event.stopPropagation();openRepo('${card.id}',${i},'editor')">⌨</button>`+
      `<button class="rb" title="Open in terminal" onclick="event.stopPropagation();openRepo('${card.id}',${i},'terminal')">❯</button>`+
      (r.github?`<button class="rb" title="Open on GitHub" onclick="event.stopPropagation();openRepo('${card.id}',${i},'github')">↗</button>`:"")+
      `</span>`;
  });
  repoHtml += `<button class="rb add" title="Manage repos" onclick="event.stopPropagation();openReposModal('${card.id}','${card.kind}','${encodeURIComponent(card.title)}')">🔗 repos</button>`;
  el.innerHTML=`<div class="ct">${esc(card.title)}</div>`+
    (card.area_title?`<div class="csub">${esc(card.area_title)}</div>`:"")+
    (card.desc?`<div class="cdesc">${esc(card.desc)}</div>`:"")+
    `<div class="cfoot"><span class="kind">${card.kind}</span>${ring(card.progress)}<span>${card.open} open${card.total?` / ${card.total}`:""}</span></div>`+
    `<div class="crepos">${repoHtml}</div>`;
  if((card.repos||[]).length) fetchPulse(card.id, el);
  return el;
}
async function fetchPulse(itemId, el){
  try{
    const d=await (await fetch("/api/pulse?item_id="+encodeURIComponent(itemId))).json();
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
  const r=await (await fetch("/api/open",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({item_id:itemId,repo_index:idx,target})})).json();
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
  const data=await (await fetch("/api/items?id=today")).json();
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
  el.innerHTML=`<div class="pt">${esc(t.title||"(untitled)")}</div>`+(t._proj?`<div class="psub">Project</div>`:(t.project_title?`<div class="psub">${esc(t.project_title)}</div>`:""));
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
function colInput(val){ const d=document.createElement("div"); d.className="col-edit";
  d.innerHTML=`<input value="${esc(val)}" onchange="persistSettings()"><button class="btn ghost" onclick="this.parentElement.remove(); persistSettings()">✕</button>`; return d; }
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
let EDIT_ORIG=null, WHEN_SEED=null;
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
async function openEdit(uuid){
  EDIT_ID=uuid;
  const data=await (await fetch("/api/item?id="+encodeURIComponent(uuid))).json();
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
  updatePills(); openOverlay("edit-overlay"); setTimeout(()=>{ autoGrow($("#f-title")); autoGrow($("#f-notes")); },0);
}
function editDirty(){
  if(!EDIT_ORIG) return false;
  const tags=$("#f-tags").value.split(",").map(s=>s.trim()).filter(Boolean).join(",");
  return $("#f-title").value!==EDIT_ORIG.title || $("#f-notes").value!==EDIT_ORIG.notes
    || tags!==EDIT_ORIG.tags || $("#f-when").value.trim()!=="" || $("#f-deadline").value.trim()!==EDIT_ORIG.deadline;
}
async function closeEdit(){
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
  const r=await (await fetch("/api/update",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})).json();
  if(!r.ok){ alert("Update failed: "+(r.error||"")); return false; }
  const it=(LIST_ITEMS||[]).find(x=>x.uuid===uuid); if(it) it.status=(field==="completed"?"completed":"canceled");
  loadSidebar(); return true;   // refresh counts; the item stays in LIST_ITEMS until next full fetch
}
function rerenderCurrent(){
  if(MODE==="cards") return renderCards(LIST_ITEMS);
  if(MODE==="matrix"){ let items=LIST_ITEMS.slice();
    if(LIST_KIND==="area") items=areaProjects(SEL.id).map(p=>({uuid:p.uuid,title:p.title,progress:p.progress,_proj:true})).concat(items);
    return renderMatrix(items); }
  if(MODE==="list") return renderRows();
}
async function completeTask(){ if(await applyStatus(EDIT_ID,"completed")){ closeOverlay("edit-overlay"); rerenderCurrent(); } }
async function cancelTask(){ if(await applyStatus(EDIT_ID,"canceled")){ closeOverlay("edit-overlay"); rerenderCurrent(); } }
async function postUpdate(body){
  const r=await (await fetch("/api/update",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})).json();
  if(!r.ok){ alert("Update failed: "+(r.error||"")); return; }
  closeOverlay("edit-overlay"); setTimeout(route,350);   // re-render current view
}
function openInThings(){ if(EDIT_ID) window.location.href="things:///show?id="+encodeURIComponent(EDIT_ID); }

// auto-organize folder (spawns your agent, review before write)
async function startOrganize(){
  const r=await (await fetch("/api/organize",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({folder_id:SEL.id})})).json();
  if(!r.ok){ alert("Organize: "+(r.error||"failed")); return; }
  openOverlay("organize-overlay");
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
  const changed=ORG_SUG.filter(s=>s.suggested_title||s.append_notes||(s.tags&&s.tags.length));
  if(!changed.length){ body.innerHTML=`<div class="empty">No suggestions — this folder looks tidy. 🎉</div>`; $("#org-actions").style.display="none"; return; }
  for(const s of changed){
    const row=document.createElement("div"); row.className="org-row"; row.dataset.uuid=s.uuid;
    let h=`<div class="org-cur">${esc(LAST_ITEMS[s.uuid]||"")}</div>`;
    if(s.suggested_title) h+=`<label class="org-line"><input type="checkbox" class="acc-title" checked data-val="${esc(s.suggested_title)}"> ✏️ ${esc(s.suggested_title)}</label>`;
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
    if(body.title||body.append_notes||body.add_tags){
      const r=await (await fetch("/api/update",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})).json();
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
  const r=await (await fetch("/api/config",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({prefs})})).json();
  if(r.ok) CONFIG=r.config;
  closeOverlay("prefs-overlay");
}

function openOverlay(id){ $("#"+id).classList.add("show"); }
function closeOverlay(id){ $("#"+id).classList.remove("show"); }
document.querySelectorAll(".overlay").forEach(o=>o.addEventListener("click",e=>{ if(e.target===o){ if(o.id==="edit-overlay") closeEdit(); else o.classList.remove("show"); } }));
document.addEventListener("keydown",e=>{ if(e.key==="Escape") document.querySelectorAll(".overlay.show").forEach(o=>{ if(o.id==="edit-overlay") closeEdit(); else o.classList.remove("show"); }); });

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
    const r=await (await fetch("/api/rename",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({id, title:name, kind:"project"})})).json();
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
  const r=await (await fetch("/api/update",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id, when})})).json();
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
  return MODE==="list"||MODE==="matrix"||MODE==="board";
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
