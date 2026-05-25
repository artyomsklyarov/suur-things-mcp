"""Things-style dashboard + saved Kanban project boards.

One two-pane UI. The sidebar holds Things' built-in lists, your saved Kanban
boards (right after Today), and your areas with nested projects. Selecting a
list/area/project shows it as a Things-style grouped list; selecting a board
shows a Kanban in the same panel.

Each board is named and scoped to chosen areas/projects (project- or area-level,
never single tasks). Columns are Things tags, so board status syncs everywhere.
Click any task to edit it; drag a card between columns to restage it. Writes go
through the URL Scheme and need THINGS_AUTH_TOKEN (read-only without it).

Run:
  - `suur-things-mcp dashboard`  → foreground (CLI), opens your browser
  - the `open_dashboard` MCP tool → background daemon thread, returns the URL
"""

from __future__ import annotations

import os
import socket
import subprocess
import threading
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from . import config as boardcfg
from . import reads
from .urlscheme import ThingsURLError, execute

DEFAULT_PORT = 8765
_running: dict[str, Any] = {}


def _auth_token() -> str | None:
    return os.environ.get("THINGS_AUTH_TOKEN")


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
        result = reads.kanban(board)
        return JSONResponse(
            {"ok": True, "auth": bool(_auth_token()), "board": board, **result}
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc), "columns": []})


async def _config_get(_request: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "config": boardcfg.load()})


async def _config_post(request: Request) -> JSONResponse:
    try:
        return JSONResponse({"ok": True, "config": boardcfg.save(await request.json())})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc)})


# --- Writes (require THINGS_AUTH_TOKEN) ------------------------------------

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


async def _move(request: Request) -> JSONResponse:
    token = _auth_token()
    if not token:
        return JSONResponse({"ok": False, "error": "THINGS_AUTH_TOKEN not set"})
    body = await request.json()
    if not body.get("id"):
        return JSONResponse({"ok": False, "error": "missing id"})
    board = boardcfg.get_board(body.get("board_id", ""))
    column_tags = set(board["columns"]) if board else set()
    new_tags = reads.tags_after_move(body["id"], body.get("column"), column_tags)
    try:
        execute("update", {"id": body["id"], "tags": ",".join(new_tags)}, auth_token=token)
        return JSONResponse({"ok": True, "tags": new_tags})
    except ThingsURLError as exc:
        return JSONResponse({"ok": False, "error": str(exc)})


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
            Route("/api/update", _update, methods=["POST"]),
            Route("/api/move", _move, methods=["POST"]),
        ]
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
<title>Things</title>
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

  .topbar { height:44px; display:flex; align-items:center; justify-content:flex-end; gap:10px;
    padding:0 16px; border-bottom:1px solid var(--divider); background:var(--main-bg); }
  .iconbtn { border:1px solid var(--divider); background:var(--main-bg); color:var(--text); width:30px;
    height:30px; border-radius:8px; cursor:pointer; font-size:15px; display:flex; align-items:center; justify-content:center; }
  .iconbtn:hover { background:var(--row-hover); }
  .views { position:absolute; top:44px; left:0; right:0; bottom:0; display:flex; }

  /* Sidebar */
  .sidebar { width:272px; flex:0 0 272px; background:var(--side-bg); overflow-y:auto;
    padding:14px 10px 20px; border-right:1px solid var(--divider); }
  .nav-item, .project { display:flex; align-items:center; gap:9px; padding:6px 10px; margin:1px 0;
    border-radius:7px; cursor:pointer; white-space:nowrap; user-select:none; }
  .project { padding-left:14px; }
  .nav-item:hover, .project:hover { background:var(--row-hover); }
  .nav-item.active, .project.active, .area-head.active { background:var(--row-sel); }
  .nav-item .ico { width:18px; text-align:center; flex:0 0 18px; font-size:14px; }
  .nav-item .label, .project .label { flex:1; overflow:hidden; text-overflow:ellipsis; }
  .nav-item .count { color:var(--muted); font-size:12.5px; font-variant-numeric:tabular-nums; }
  .nav-item.add { color:var(--muted); }
  .nav-sep { height:14px; }
  .area-head { padding:7px 10px 3px; margin-top:8px; font-weight:600; font-size:13.5px;
    display:flex; align-items:center; gap:8px; white-space:nowrap; cursor:pointer; border-radius:7px; }
  .area-head:hover { background:var(--row-hover); }
  .area-head .stack { color:var(--muted); font-size:12px; }
  svg.ring { flex:0 0 16px; }
  .ring-bg { fill:none; stroke:var(--ring-bg); stroke-width:2; }
  .ring-fg { fill:none; stroke:var(--ring-fg); stroke-width:2; stroke-linecap:round; }

  /* Main */
  .main { flex:1; min-width:0; display:flex; flex-direction:column; }
  .main-head { display:flex; align-items:center; gap:11px; padding:26px 40px 0; margin-bottom:18px; flex:none; }
  .main-head .ico { font-size:24px; } .main-head h1 { font-size:23px; font-weight:700; margin:0; }
  .main-head .grow { flex:1; }
  #content { flex:1; min-height:0; overflow-y:auto; padding:0 40px 80px; }
  .main.board-mode #content { overflow:hidden; padding:0 18px 18px; }
  .board-wrap { display:flex; gap:14px; align-items:flex-start; height:100%; overflow-x:auto; }

  .group-head { display:flex; align-items:center; gap:8px; font-weight:600; font-size:14.5px;
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

  /* Kanban columns */
  .col { background:var(--col-bg); border-radius:12px; width:300px; flex:0 0 300px; max-height:100%;
    display:flex; flex-direction:column; }
  .col-head { padding:13px 15px 9px; font-weight:600; font-size:13px; text-transform:uppercase;
    letter-spacing:.03em; color:var(--muted); display:flex; justify-content:space-between; }
  .col-cards { padding:0 9px 12px; overflow-y:auto; min-height:24px; }
  .col.drop { outline:2px dashed var(--accent); outline-offset:-4px; border-radius:12px; }
  .card { background:var(--card-bg); border-radius:9px; padding:10px 12px; margin:7px 0;
    box-shadow:var(--card-shadow); cursor:pointer; }
  .card.dragging { opacity:.4; }
  .card .ct { font-weight:500; margin-bottom:2px; }
  .card .csub { color:var(--muted); font-size:12px; }
  .card .cmeta { margin-top:7px; display:flex; flex-wrap:wrap; gap:5px; align-items:center; }

  /* Modals */
  .overlay { position:fixed; inset:0; background:var(--overlay); display:none; align-items:flex-start;
    justify-content:center; z-index:20; padding:60px 16px; }
  .overlay.show { display:flex; }
  .panel { background:var(--main-bg); border-radius:14px; width:520px; max-width:100%; max-height:84vh;
    overflow-y:auto; box-shadow:0 16px 50px rgba(0,0,0,.35); padding:22px 24px; }
  .panel h2 { margin:0 0 16px; font-size:18px; }
  .field { margin-bottom:14px; } .field label { display:block; font-size:12px; color:var(--muted); margin-bottom:5px; }
  .field input:not([type=checkbox]), .field textarea { width:100%; font:inherit; color:var(--text);
    background:var(--side-bg); border:1px solid var(--divider); border-radius:8px; padding:8px 10px; }
  .field input[type=checkbox] { width:16px; height:16px; flex:0 0 16px; margin:0; }
  .field textarea { min-height:80px; resize:vertical; }
  .checks { margin:8px 0 0; line-height:1.8; } .checks .ci { color:var(--muted); font-size:13px; }
  .checks .ci.done { text-decoration:line-through; }
  .btnrow { display:flex; gap:8px; flex-wrap:wrap; margin-top:18px; align-items:center; }
  .btn { font:inherit; padding:7px 15px; border-radius:8px; border:1px solid var(--divider);
    background:var(--main-bg); color:var(--text); cursor:pointer; }
  .btn:hover { background:var(--row-hover); }
  .btn.primary { background:var(--accent); border-color:var(--accent); color:#fff; }
  .btn.danger { color:var(--red); }
  .btn.ghost { border:0; color:var(--muted); }
  .spacer { flex:1; }
  .hint { font-size:12px; color:var(--muted); margin-top:6px; } .hint.warn { color:var(--red); }
  .col-edit { display:flex; gap:6px; margin:5px 0; align-items:center; } .col-edit input { flex:1; }
  .area-pick { font-weight:600; margin:12px 0 4px; } .proj-pick { padding-left:18px; }
  .pick { display:flex; align-items:center; gap:8px; padding:3px 0; cursor:pointer; font-weight:400; }
</style>
</head>
<body>
<div class="topbar">
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

<!-- Edit dialog -->
<div class="overlay" id="edit-overlay">
  <div class="panel">
    <h2 id="edit-context"></h2>
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

<!-- Board settings dialog -->
<div class="overlay" id="settings-overlay">
  <div class="panel">
    <h2>Board settings</h2>
    <div class="field"><label>Board name</label><input id="b-name"></div>
    <div class="field">
      <label>Columns (each is a Things tag name)</label>
      <div id="cols-edit"></div>
      <button class="btn" style="margin-top:6px" onclick="addCol()">+ Add column</button>
      <div class="hint">Tip: create these as tags in Things (optionally nested under a "Kanban" tag). A card shows in the column whose tag it carries.</div>
    </div>
    <div class="field">
      <label>Include on board — a whole area, or specific projects</label>
      <div id="includes"></div>
    </div>
    <div class="btnrow">
      <button class="btn primary" onclick="saveBoardSettings()">Save</button>
      <button class="btn danger" onclick="deleteBoard()">Delete board</button>
      <span class="spacer"></span>
      <button class="btn ghost" onclick="closeOverlay('settings-overlay')">Cancel</button>
    </div>
  </div>
</div>

<script>
const $ = (s, r=document) => r.querySelector(s);
let AUTH = false, SIDEBAR = null, BOARDS = [];
let SEL = {id:"today", icon:"⭐", title:"Today", kind:"builtin"};
let MODE = "list";        // "list" | "board"
let CUR_BOARD = null;     // board id when MODE==="board"
let EDIT_ID = null;
const DEFAULT_COLUMNS = ["Backlog","In Progress","On Hold","Done"];
function esc(s){ return String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
function uid(){ return Math.random().toString(36).slice(2,10); }

// --- theme ---
function applyTheme(t){ document.documentElement.setAttribute("data-theme", t);
  $("#theme").textContent = t === "dark" ? "☀" : "☾"; localStorage.setItem("things-theme", t); }
applyTheme(localStorage.getItem("things-theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
$("#theme").onclick = () => applyTheme(document.documentElement.getAttribute("data-theme")==="dark" ? "light" : "dark");

function ring(p){
  const r=6, c=2*Math.PI*r, off=c*(1-p);
  if (p<=0) return `<svg class="ring" width="16" height="16" viewBox="0 0 16 16"><circle class="ring-bg" cx="8" cy="8" r="6"/></svg>`;
  return `<svg class="ring" width="16" height="16" viewBox="0 0 16 16"><circle class="ring-bg" cx="8" cy="8" r="6"/>`+
    `<circle class="ring-fg" cx="8" cy="8" r="6" stroke-dasharray="${c.toFixed(2)}" stroke-dashoffset="${off.toFixed(2)}" transform="rotate(-90 8 8)"/></svg>`;
}

// --- sidebar ---
async function loadConfig(){ BOARDS = (await (await fetch("/api/config")).json()).config.boards; }
async function loadSidebar(){
  const data = await (await fetch("/api/sidebar")).json();
  AUTH = !!data.auth;
  const el = $("#sidebar"); el.innerHTML = "";
  if (!data.ok){ el.innerHTML = `<div class="err">${esc(data.error||"error")}</div>`; return; }
  SIDEBAR = data.sidebar;
  const bi = SIDEBAR.builtins, tIdx = bi.findIndex(b=>b.id==="today");
  bi.slice(0, tIdx+1).forEach(b => el.appendChild(builtinEl(b)));
  // Boards — right after Today
  BOARDS.forEach(b => el.appendChild(boardNavEl(b)));
  el.appendChild(addBoardEl());
  bi.slice(tIdx+1).forEach(b => el.appendChild(builtinEl(b)));
  el.appendChild(Object.assign(document.createElement("div"),{className:"nav-sep"}));
  const areas = SIDEBAR.areas.concat(SIDEBAR.arealess.length ? [{uuid:null,title:"Projects",projects:SIDEBAR.arealess}] : []);
  for (const a of areas){
    const head = document.createElement("div");
    head.className="area-head"; if(a.uuid) head.dataset.id=a.uuid;
    head.innerHTML = `<span class="stack">▥</span><span class="label">${esc(a.title)}</span>`;
    if(a.uuid) head.onclick = () => select({id:a.uuid, icon:"▥", title:a.title, kind:"area"});
    el.appendChild(head);
    for (const p of a.projects){
      const row = document.createElement("div");
      row.className="project"; row.dataset.id=p.uuid;
      row.innerHTML = `${ring(p.progress)}<span class="label">${esc(p.title)}</span>`;
      row.onclick = () => select({id:p.uuid, icon:"", title:p.title, kind:"project"});
      el.appendChild(row);
    }
  }
}
function builtinEl(b){
  const row = document.createElement("div");
  row.className="nav-item"; row.dataset.id=b.id;
  row.innerHTML = `<span class="ico">${b.icon}</span><span class="label">${esc(b.title)}</span>`+
    (b.count!=null ? `<span class="count">${b.count}</span>` : "");
  row.onclick = () => select({id:b.id, icon:b.icon, title:b.title, kind:"builtin"});
  return row;
}
function boardNavEl(b){
  const row = document.createElement("div");
  row.className="nav-item"; row.dataset.id=b.id;
  row.innerHTML = `<span class="ico">📋</span><span class="label">${esc(b.name)}</span>`;
  row.onclick = () => showBoard(b.id);
  return row;
}
function addBoardEl(){
  const row = document.createElement("div");
  row.className="nav-item add";
  row.innerHTML = `<span class="ico">＋</span><span class="label">New board</span>`;
  row.onclick = newBoard;
  return row;
}
function setActive(id){
  document.querySelectorAll(".nav-item,.area-head,.project").forEach(n =>
    n.classList.toggle("active", n.dataset.id === String(id)));
}

// --- list view ---
async function select(sel){
  MODE = "list"; CUR_BOARD = null; SEL = sel;
  $(".main").classList.remove("board-mode"); $("#board-gear").style.display="none";
  setActive(sel.id);
  $("#head-ico").textContent = sel.icon || ""; $("#head-title").textContent = sel.title;
  const c = $("#content"); c.innerHTML = `<div class="empty">loading…</div>`;
  const data = await (await fetch("/api/items?id="+encodeURIComponent(sel.id))).json();
  if (!data.ok){ c.innerHTML = `<div class="err">${esc(data.error||"error")}</div>`; return; }
  renderList(data.items, data.kind);
}
function groupBy(items, key){
  const groups=[], idx={};
  for (const it of items){ const k = it[key]||"\\u0000";
    if(!(k in idx)){ idx[k]=groups.length; groups.push({key:it[key]||null, items:[]}); }
    groups[idx[k]].items.push(it); }
  return groups;
}
function renderList(items, kind){
  const c = $("#content"); c.innerHTML="";
  if(!items.length){ c.innerHTML=`<div class="empty">Nothing here.</div>`; return; }
  const key = kind==="project" ? "heading_title" : "project_title";
  const groups = groupBy(items, key).sort((a,b)=>(a.key?1:0)-(b.key?1:0));
  for (const g of groups){
    if(g.key){ const h=document.createElement("div"); h.className="group-head"; h.textContent=g.key; c.appendChild(h); }
    for (const it of g.items) c.appendChild(rowEl(it));
  }
}
function metaHtml(it){
  let m="";
  if (it.has_notes) m += `<span class="note-ico">📄</span>`;
  (it.tags||[]).forEach(t => m += `<span class="pill">${esc(t)}</span>`);
  if (it.deadline){ const od = it.deadline < new Date().toISOString().slice(0,10);
    m += `<span class="due">${od?'<span class="dot"></span>':"⚑"} ${it.deadline}</span>`; }
  return m;
}
function rowEl(it){
  const done = it.status==="completed", cancel = it.status==="canceled";
  const row = document.createElement("div");
  row.className = "row"+(done||cancel?" is-done":"");
  row.onclick = () => openEdit(it.uuid);
  const m = metaHtml(it);
  row.innerHTML = `<span class="box ${done?"done":cancel?"cancel":""}"></span>`+
    `<span class="title">${esc(it.title||"(untitled)")}</span>`+(m?`<span class="meta">${m}</span>`:"");
  return row;
}

// --- board view (in main panel) ---
async function showBoard(id){
  MODE = "board"; CUR_BOARD = id;
  setActive(id);
  $(".main").classList.add("board-mode"); $("#board-gear").style.display="flex";
  const b = BOARDS.find(x=>x.id===id);
  $("#head-ico").textContent = "📋"; $("#head-title").textContent = b ? b.name : "Board";
  const c = $("#content"); c.innerHTML = `<div class="empty">loading…</div>`;
  const data = await (await fetch("/api/board?id="+encodeURIComponent(id))).json();
  AUTH = !!data.auth;
  if (!data.ok){ c.innerHTML = `<div class="err">${esc(data.error||"error")}</div>`; return; }
  c.innerHTML = "";
  const wrap = document.createElement("div"); wrap.className="board-wrap";
  if (!data.columns.length){ wrap.innerHTML = `<div class="empty">No columns yet. Open ⚙ to add columns and include projects/areas.</div>`; }
  for (const col of data.columns) wrap.appendChild(colEl(col, id));
  c.appendChild(wrap);
}
function colEl(col, boardId){
  const c = document.createElement("div"); c.className="col";
  c.innerHTML = `<div class="col-head"><span>${esc(col.title)}</span><span>${col.cards.length}</span></div>`;
  const list = document.createElement("div"); list.className="col-cards";
  for (const card of col.cards) list.appendChild(cardEl(card));
  c.addEventListener("dragover", e => { if(AUTH){ e.preventDefault(); c.classList.add("drop"); } });
  c.addEventListener("dragleave", () => c.classList.remove("drop"));
  c.addEventListener("drop", e => { e.preventDefault(); c.classList.remove("drop");
    const id = e.dataTransfer.getData("text/id"); if(id) moveCard(id, col.name, boardId); });
  c.appendChild(list);
  return c;
}
function cardEl(card){
  const el = document.createElement("div"); el.className="card"; el.draggable = AUTH;
  el.onclick = () => openEdit(card.uuid);
  el.addEventListener("dragstart", e => { e.dataTransfer.setData("text/id", card.uuid); el.classList.add("dragging"); });
  el.addEventListener("dragend", () => el.classList.remove("dragging"));
  const tags = (card.tags||[]).map(t=>`<span class="pill">${esc(t)}</span>`).join("");
  const due = card.deadline ? `<span class="due"><span class="dot"></span>${card.deadline}</span>` : "";
  el.innerHTML = `<div class="ct">${esc(card.title||"(untitled)")}</div>`+
    (card.project_title?`<div class="csub">${esc(card.project_title)}</div>`:"")+
    ((tags||due||card.has_notes)?`<div class="cmeta">${card.has_notes?'<span class="note-ico">📄</span>':""}${tags}${due}</div>`:"");
  return el;
}
async function moveCard(id, column, boardId){
  const r = await (await fetch("/api/move",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({id, column, board_id:boardId})})).json();
  if(!r.ok){ alert("Move failed: "+(r.error||"")); }
  showBoard(boardId);
}

// --- board create/settings ---
async function newBoard(){
  const b = {id:uid(), name:"New Board", columns:[...DEFAULT_COLUMNS], include_areas:[], include_projects:[]};
  BOARDS.push(b); await persistBoards();
  await loadSidebar(); showBoard(b.id); openBoardSettings();
}
async function persistBoards(){
  const r = await (await fetch("/api/config",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({boards:BOARDS})})).json();
  if(r.ok) BOARDS = r.config.boards;
}
function openBoardSettings(){
  const b = BOARDS.find(x=>x.id===CUR_BOARD); if(!b) return;
  $("#b-name").value = b.name;
  const ce = $("#cols-edit"); ce.innerHTML = "";
  (b.columns||[]).forEach(c => ce.appendChild(colInput(c)));
  const inc = $("#includes"); inc.innerHTML = "";
  const areaSet = new Set(b.include_areas||[]), projSet = new Set(b.include_projects||[]);
  for (const a of (SIDEBAR.areas||[])){
    const ah = document.createElement("div"); ah.className="area-pick";
    ah.innerHTML = `<label class="pick"><input type="checkbox" data-area="${a.uuid}" ${areaSet.has(a.uuid)?"checked":""}> ${esc(a.title)} <span style="color:var(--muted);font-weight:400">(entire area)</span></label>`;
    inc.appendChild(ah);
    for (const p of a.projects){
      const pe = document.createElement("div"); pe.className="proj-pick";
      pe.innerHTML = `<label class="pick"><input type="checkbox" data-project="${p.uuid}" ${projSet.has(p.uuid)?"checked":""}> ${esc(p.title)}</label>`;
      inc.appendChild(pe);
    }
  }
  openOverlay("settings-overlay");
}
function colInput(val){
  const d = document.createElement("div"); d.className="col-edit";
  d.innerHTML = `<input value="${esc(val)}"><button class="btn ghost" onclick="this.parentElement.remove()">✕</button>`;
  return d;
}
function addCol(){ $("#cols-edit").appendChild(colInput("")); }
async function saveBoardSettings(){
  const b = BOARDS.find(x=>x.id===CUR_BOARD); if(!b) return;
  b.name = $("#b-name").value.trim() || "Untitled board";
  b.columns = [...document.querySelectorAll("#cols-edit input")].map(i=>i.value.trim()).filter(Boolean);
  b.include_areas = [...document.querySelectorAll("#includes input[data-area]:checked")].map(i=>i.dataset.area);
  b.include_projects = [...document.querySelectorAll("#includes input[data-project]:checked")].map(i=>i.dataset.project);
  await persistBoards();
  closeOverlay("settings-overlay");
  await loadSidebar(); showBoard(CUR_BOARD);
}
async function deleteBoard(){
  if(!confirm("Delete this board? (Your tasks and tags in Things are untouched.)")) return;
  BOARDS = BOARDS.filter(x=>x.id!==CUR_BOARD); await persistBoards();
  closeOverlay("settings-overlay");
  await loadSidebar(); select({id:"today", icon:"⭐", title:"Today", kind:"builtin"});
}

// --- edit dialog ---
async function openEdit(uuid){
  EDIT_ID = uuid;
  const data = await (await fetch("/api/item?id="+encodeURIComponent(uuid))).json();
  if(!data.ok){ alert("Could not load task."); return; }
  const it = data.item;
  $("#edit-context").textContent = it.project_title || "Task";
  $("#f-title").value = it.title || ""; $("#f-notes").value = it.notes || "";
  $("#f-when").value = ""; $("#f-deadline").value = it.deadline || "";
  $("#f-tags").value = (it.tags||[]).join(", ");
  const cl = $("#f-checklist");
  cl.innerHTML = (it.checklist||[]).length
    ? `<div class="field"><label>Checklist</label><div class="checks">`+
      it.checklist.map(c=>`<div class="ci ${c.status==="completed"?"done":""}">${c.status==="completed"?"☑":"☐"} ${esc(c.title)}</div>`).join("")+`</div></div>`
    : "";
  const ro = !AUTH;
  $("#edit-warn").style.display = ro ? "block" : "none";
  ["f-title","f-notes","f-when","f-deadline","f-tags"].forEach(id => $("#"+id).disabled = ro);
  $("#save-btn").disabled = ro;
  openOverlay("edit-overlay");
}
async function saveEdit(){
  const tags = $("#f-tags").value.split(",").map(s=>s.trim()).filter(Boolean);
  const body = { id:EDIT_ID, title:$("#f-title").value, notes:$("#f-notes").value, tags };
  const when = $("#f-when").value.trim(); if(when) body.when = when;
  body.deadline = $("#f-deadline").value.trim();
  await postUpdate(body);
}
async function completeTask(){ await postUpdate({id:EDIT_ID, completed:true}); }
async function cancelTask(){ await postUpdate({id:EDIT_ID, canceled:true}); }
async function postUpdate(body){
  const r = await (await fetch("/api/update",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify(body)})).json();
  if(!r.ok){ alert("Update failed: "+(r.error||"")); return; }
  closeOverlay("edit-overlay");
  setTimeout(() => { MODE==="board" ? showBoard(CUR_BOARD) : select(SEL); }, 350);
}
function openInThings(){ if(EDIT_ID) window.location.href = "things:///show?id="+encodeURIComponent(EDIT_ID); }

// --- overlays ---
function openOverlay(id){ $("#"+id).classList.add("show"); }
function closeOverlay(id){ $("#"+id).classList.remove("show"); }
document.querySelectorAll(".overlay").forEach(o => o.addEventListener("click", e => { if(e.target===o) o.classList.remove("show"); }));
document.addEventListener("keydown", e => { if(e.key==="Escape") document.querySelectorAll(".overlay.show").forEach(o=>o.classList.remove("show")); });

// --- boot ---
(async () => { await loadConfig(); await loadSidebar(); select(SEL); })();
</script>
</body>
</html>
"""
