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

import os
import re
import shutil
import socket
import subprocess
import threading
from typing import Any
from urllib.parse import urlparse

import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from . import config as boardcfg
from . import reads
from .urlscheme import ThingsURLError, execute

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
    return HTMLResponse(INDEX_HTML)


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
    if body.get("completed"):
        params["completed"] = True
    if body.get("canceled"):
        params["canceled"] = True
    try:
        execute("update", params, auth_token=token)
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


def create_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/", _index),
            Route("/api/state", _state),
            Route("/api/sidebar", _sidebar),
            Route("/api/items", _items),
            Route("/api/item", _item),
            Route("/api/board", _board),
            Route("/api/config", _config_get),
            Route("/api/config", _config_post, methods=["POST"]),
            Route("/api/link", _link_post, methods=["POST"]),
            Route("/api/update", _update, methods=["POST"]),
            Route("/api/open", _open, methods=["POST"]),
        ],
        middleware=[Middleware(_OriginGuard)],
    )


# --- Server lifecycle -----------------------------------------------------

def _pick_port(preferred: int = DEFAULT_PORT) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
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
    chosen = _pick_port(port)
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
  }
  html[data-theme="dark"] {
    --side-bg:#23272c; --main-bg:#1b1e23; --text:#e7e9ec; --muted:#888e97;
    --divider:#31363c; --row-hover:#2b3035; --row-sel:#384049; --accent:#4c8dff;
    --pill-border:#474d55; --ring-bg:#3a3f46; --ring-fg:#888e97; --badge:#363b42;
    --red:#ff6453; --check-border:#5a6068; --header-rule:#2e333a; --col-bg:#22262b;
    --card-bg:#2b3036; --card-shadow:0 1px 2px rgba(0,0,0,.3); --overlay:rgba(0,0,0,.5);
  }
  * { box-sizing:border-box; }
  html, body { height:100%; margin:0; overflow:hidden; }
  body { font:14px/1.45 -apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif;
    background:var(--main-bg); color:var(--text); -webkit-font-smoothing:antialiased; }

  .topbar { height:44px; display:flex; align-items:center; gap:10px; padding:0 16px;
    border-bottom:1px solid var(--divider); background:var(--main-bg); }
  .brand { font-weight:800; font-size:13px; letter-spacing:.13em; }
  .grow { flex:1; }
  .iconbtn { border:1px solid var(--divider); background:var(--main-bg); color:var(--text); width:30px;
    height:30px; border-radius:8px; cursor:pointer; font-size:15px; display:flex; align-items:center; justify-content:center; flex:0 0 30px; }
  .iconbtn:hover { background:var(--row-hover); }
  .views { position:absolute; top:44px; left:0; right:0; bottom:0; display:flex; }

  .sidebar { width:272px; flex:0 0 272px; background:var(--side-bg); overflow-y:auto;
    padding:14px 10px 20px; border-right:1px solid var(--divider); }
  .nav-item, .project { display:flex; align-items:center; gap:9px; padding:6px 10px; margin:1px 0;
    border-radius:7px; cursor:pointer; white-space:nowrap; user-select:none; }
  .project { padding-left:14px; }
  .nav-item:hover, .project:hover { background:var(--row-hover); }
  .nav-item.active, .project.active, .area-head.active { background:var(--row-sel); }
  .nav-item .ico, .project .ico { width:18px; text-align:center; flex:0 0 18px; font-size:14px; }
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
  .main-head .ico { font-size:24px; } .main-head h1 { font-size:23px; font-weight:700; margin:0; }
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
  .box.done { background:var(--accent); border-color:var(--accent); }
  .box.done::after { content:"✓"; color:#fff; font-size:11px; font-weight:700; }
  .box.cancel { background:var(--muted); border-color:var(--muted); }
  .box.cancel::after { content:"✕"; color:#fff; font-size:10px; font-weight:700; }
  .title { flex:1 1 auto; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .meta { display:flex; align-items:center; gap:6px; flex:0 0 auto; }
  .pill { font-size:11.5px; padding:1px 8px; border:1px solid var(--pill-border); color:var(--muted); border-radius:11px; white-space:nowrap; }
  .note-ico { color:var(--muted); font-size:12px; }
  .due { display:inline-flex; align-items:center; gap:4px; color:var(--red); font-size:12px; white-space:nowrap; }
  .due .dot { width:9px; height:9px; border-radius:50%; background:var(--red); display:inline-block; }
  .empty, .err { color:var(--muted); padding:40px 4px; } .err { color:var(--red); }
  .proj-notes { color:var(--muted); font-size:14px; line-height:1.55; margin:-4px 0 18px; max-width:760px; white-space:pre-wrap; }
  .proj-notes a { color:var(--accent); }

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
  <span class="grow"></span>
  <button class="iconbtn" id="prefs-btn" title="Preferences" onclick="openPrefs()">⚙</button>
  <button class="iconbtn" id="theme" title="Toggle light/dark">◐</button>
</div>
<div class="views">
  <aside class="sidebar" id="sidebar"></aside>
  <main class="main">
    <div class="main-head">
      <span class="ico" id="head-ico">⭐</span><h1 id="head-title">Today</h1>
      <span class="grow"></span>
      <button class="iconbtn" id="board-gear" title="Board settings" style="display:none" onclick="openBoardSettings()">⚙</button>
    </div>
    <div id="content"></div>
  </main>
</div>

<div class="overlay" id="edit-overlay">
  <div class="panel">
    <h2 id="edit-context"></h2><div class="sub">Edit task</div>
    <div class="field"><label>Title</label><input id="f-title"></div>
    <div class="field"><label>Notes</label><textarea id="f-notes"></textarea></div>
    <div class="field"><label>When (today / tomorrow / anytime / someday / yyyy-mm-dd)</label><input id="f-when" placeholder="leave blank to keep"></div>
    <div class="field"><label>Deadline (yyyy-mm-dd, blank = unchanged)</label><input id="f-deadline"></div>
    <div class="field"><label>Tags (comma separated)</label><input id="f-tags"></div>
    <div id="f-checklist"></div>
    <div class="hint warn" id="edit-warn" style="display:none">Read-only: set THINGS_AUTH_TOKEN to edit.</div>
    <div class="btnrow">
      <button class="btn primary" id="save-btn" onclick="saveEdit()">Save</button>
      <button class="btn" onclick="completeTask()">Complete</button>
      <button class="btn" onclick="cancelTask()">Cancel task</button>
      <span class="spacer"></span>
      <button class="btn ghost" onclick="openInThings()">Open in Things ↗</button>
      <button class="btn ghost" onclick="closeOverlay('edit-overlay')">Close</button>
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
let COLLAPSED=new Set(JSON.parse(localStorage.getItem("collapsed-areas")||"[]"));
const DEFAULT_COLUMNS=["Backlog","In Progress","On Hold","Done"];
const QUADS=[
  {key:"do",title:"Do First",sub:"Urgent · Important",cls:"q-do"},
  {key:"schedule",title:"Schedule",sub:"Important · Not urgent",cls:"q-sched"},
  {key:"delegate",title:"Delegate",sub:"Urgent · Not important",cls:"q-deleg"},
  {key:"eliminate",title:"Don't Do",sub:"Neither",cls:"q-elim"},
];
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
  if(h==="#p") return renderPriority();
  if(h.startsWith("#b/")){ const id=decodeURIComponent(h.slice(3)); if(CONFIG.boards.find(b=>b.id===id)) return renderBoard(id); }
  if(h.startsWith("#l/")){ const sel=resolveList(decodeURIComponent(h.slice(3))); if(sel) return renderList(sel); }
  return go("#l/today");
}
window.addEventListener("hashchange", route);

// --- sidebar ---
async function loadSidebar(){
  const data=await (await fetch("/api/sidebar")).json();
  AUTH=!!data.auth; if(!data.ok){ $("#sidebar").innerHTML=`<div class="err">${esc(data.error||"error")}</div>`; return; }
  SIDEBAR=data.sidebar; renderSidebar();
}
function renderSidebar(){
  const el=$("#sidebar"); el.innerHTML="";
  const bi=SIDEBAR.builtins, tIdx=bi.findIndex(b=>b.id==="today");
  bi.slice(0,tIdx+1).forEach(b=>el.appendChild(builtinEl(b)));
  const pri=document.createElement("div"); pri.className="nav-item"; pri.dataset.id="priority";
  pri.innerHTML=`<span class="ico">◰</span><span class="label">Priority Square</span>`; pri.onclick=()=>go("#p");
  el.appendChild(pri);
  const gh=document.createElement("div"); gh.className="group-head";
  gh.innerHTML=`<span>Boards</span><span class="add" title="New board">＋</span>`;
  gh.querySelector(".add").onclick=(e)=>{e.stopPropagation(); newBoard();};
  el.appendChild(gh);
  CONFIG.boards.forEach(b=>{
    const row=document.createElement("div"); row.className="project"; row.dataset.id=b.id;
    row.innerHTML=`<span class="ico">📋</span><span class="label">${esc(b.name)}</span>`;
    row.onclick=()=>go("#b/"+encodeURIComponent(b.id)); el.appendChild(row);
  });
  bi.slice(tIdx+1).forEach(b=>el.appendChild(builtinEl(b)));
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
  setActive(CURRENT_ID);
}
function toggleArea(uuid){ COLLAPSED.has(uuid)?COLLAPSED.delete(uuid):COLLAPSED.add(uuid);
  localStorage.setItem("collapsed-areas", JSON.stringify([...COLLAPSED])); renderSidebar(); }
function builtinEl(b){
  const row=document.createElement("div"); row.className="nav-item"; row.dataset.id=b.id;
  row.innerHTML=`<span class="ico">${b.icon}</span><span class="label">${esc(b.title)}</span>`+(b.count!=null?`<span class="count">${b.count}</span>`:"");
  row.onclick=()=>go("#l/"+encodeURIComponent(b.id)); return row;
}
function setActive(id){ CURRENT_ID=id; document.querySelectorAll(".nav-item,.area-head,.project").forEach(n=>n.classList.toggle("active", n.dataset.id===String(id))); }
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
async function renderList(sel){
  MODE="list"; CUR_BOARD=null; SEL=sel;
  $(".main").classList.remove("fill"); $("#board-gear").style.display="none"; setActive(sel.id);
  $("#head-ico").textContent=sel.icon||""; $("#head-title").textContent=sel.title;
  const c=$("#content"); c.innerHTML=`<div class="empty">loading…</div>`;
  const data=await (await fetch("/api/items?id="+encodeURIComponent(sel.id))).json();
  if(!data.ok){ c.innerHTML=`<div class="err">${esc(data.error||"error")}</div>`; return; }
  const items=data.items, kind=data.kind; c.innerHTML="";
  if(data.notes){ const n=document.createElement("div"); n.className="proj-notes"; n.innerHTML=linkify(data.notes); c.appendChild(n); }
  if(!items.length){ const e=document.createElement("div"); e.className="empty"; e.textContent="Nothing here."; c.appendChild(e); return; }
  const key=kind==="project"?"heading_title":"project_title";
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
  const m=metaHtml(it);
  row.innerHTML=`<span class="box ${done?"done":cancel?"cancel":""}"></span><span class="title">${esc(it.title||"(untitled)")}</span>`+(m?`<span class="meta">${m}</span>`:"");
  return row;
}

// --- board view ---
async function renderBoard(id){
  MODE="board"; CUR_BOARD=id; setActive(id);
  $(".main").classList.add("fill"); $("#board-gear").style.display="flex";
  const b=CONFIG.boards.find(x=>x.id===id);
  $("#head-ico").textContent="📋"; $("#head-title").textContent=b?b.name:"Board";
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
  return el;
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

// --- priority square ---
async function renderPriority(){
  MODE="priority"; CUR_BOARD=null; setActive("priority");
  $(".main").classList.add("fill"); $("#board-gear").style.display="none";
  $("#head-ico").textContent="◰"; $("#head-title").textContent="Priority Square";
  const c=$("#content"); c.innerHTML=`<div class="empty">loading…</div>`;
  const data=await (await fetch("/api/items?id=today")).json();
  TODAY_CACHE=data.ok?data.items:[]; drawPriority();
}
function drawPriority(){
  const c=$("#content"); c.innerHTML="";
  const pr=CONFIG.priority||{};
  const wrap=document.createElement("div"); wrap.className="pri-wrap";
  const pool=document.createElement("div"); pool.className="pri-pool";
  const unassigned=TODAY_CACHE.filter(t=>!QUADS.some(q=>q.key===pr[t.uuid]));
  pool.innerHTML=`<div class="col-head"><span>Today</span><span>${unassigned.length}</span></div>`;
  const pc=document.createElement("div"); pc.className="col-cards";
  if(!unassigned.length) pc.innerHTML=`<div class="empty" style="padding:16px 6px">All sorted 🎉</div>`;
  unassigned.forEach(t=>pc.appendChild(priCardEl(t))); pool.appendChild(pc); dropZone(pool,null); wrap.appendChild(pool);
  const matrix=document.createElement("div"); matrix.className="matrix";
  for(const q of QUADS){
    const quad=document.createElement("div"); quad.className="quad "+q.cls;
    quad.innerHTML=`<div class="quad-head"><div class="qt">${q.title}</div><div class="qs">${q.sub}</div></div>`;
    const cards=document.createElement("div"); cards.className="cards";
    TODAY_CACHE.filter(t=>pr[t.uuid]===q.key).forEach(t=>cards.appendChild(priCardEl(t)));
    quad.appendChild(cards); dropZone(quad,q.key); matrix.appendChild(quad);
  }
  wrap.appendChild(matrix); c.appendChild(wrap);
}
function priCardEl(t){
  const el=document.createElement("div"); el.className="pcard"; el.draggable=true; el.onclick=()=>openEdit(t.uuid);
  el.addEventListener("dragstart",e=>{ e.dataTransfer.setData("text/id",t.uuid); el.classList.add("dragging"); });
  el.addEventListener("dragend",()=>el.classList.remove("dragging"));
  el.innerHTML=`<div class="pt">${esc(t.title||"(untitled)")}</div>`+(t.project_title?`<div class="psub">${esc(t.project_title)}</div>`:"");
  return el;
}
function dropZone(elm,quad){
  elm.addEventListener("dragover",e=>{ e.preventDefault(); elm.classList.add("drop"); });
  elm.addEventListener("dragleave",()=>elm.classList.remove("drop"));
  elm.addEventListener("drop",e=>{ e.preventDefault(); elm.classList.remove("drop");
    const id=e.dataTransfer.getData("text/id"); if(!id) return;
    CONFIG.priority=CONFIG.priority||{}; if(quad) CONFIG.priority[id]=quad; else delete CONFIG.priority[id];
    saveConfig().then(drawPriority);
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

// --- edit dialog ---
async function openEdit(uuid){
  EDIT_ID=uuid;
  const data=await (await fetch("/api/item?id="+encodeURIComponent(uuid))).json();
  if(!data.ok){ alert("Could not load task."); return; }
  const it=data.item;
  $("#edit-context").textContent=it.project_title||"Task";
  $("#f-title").value=it.title||""; $("#f-notes").value=it.notes||""; $("#f-when").value="";
  $("#f-deadline").value=it.deadline||""; $("#f-tags").value=(it.tags||[]).join(", ");
  $("#f-checklist").innerHTML=(it.checklist||[]).length
    ? `<div class="field"><label>Checklist</label><div class="checks">`+it.checklist.map(c=>`<div class="ci ${c.status==="completed"?"done":""}">${c.status==="completed"?"☑":"☐"} ${esc(c.title)}</div>`).join("")+`</div></div>` : "";
  const ro=!AUTH; $("#edit-warn").style.display=ro?"block":"none";
  ["f-title","f-notes","f-when","f-deadline","f-tags"].forEach(id=>$("#"+id).disabled=ro); $("#save-btn").disabled=ro;
  openOverlay("edit-overlay");
}
async function saveEdit(){
  const tags=$("#f-tags").value.split(",").map(s=>s.trim()).filter(Boolean);
  const body={id:EDIT_ID,title:$("#f-title").value,notes:$("#f-notes").value,tags};
  const when=$("#f-when").value.trim(); if(when) body.when=when;
  body.deadline=$("#f-deadline").value.trim(); await postUpdate(body);
}
async function completeTask(){ await postUpdate({id:EDIT_ID,completed:true}); }
async function cancelTask(){ await postUpdate({id:EDIT_ID,canceled:true}); }
async function postUpdate(body){
  const r=await (await fetch("/api/update",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})).json();
  if(!r.ok){ alert("Update failed: "+(r.error||"")); return; }
  closeOverlay("edit-overlay"); setTimeout(route,350);   // re-render current view
}
function openInThings(){ if(EDIT_ID) window.location.href="things:///show?id="+encodeURIComponent(EDIT_ID); }

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
document.querySelectorAll(".overlay").forEach(o=>o.addEventListener("click",e=>{ if(e.target===o) o.classList.remove("show"); }));
document.addEventListener("keydown",e=>{ if(e.key==="Escape") document.querySelectorAll(".overlay.show").forEach(o=>o.classList.remove("show")); });

(async()=>{ await loadConfig(); await loadSidebar(); route(); })();
</script>
</body>
</html>
"""
