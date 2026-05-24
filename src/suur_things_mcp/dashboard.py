"""Things-style read-only dashboard.

A faithful two-pane replica of Things: a left sidebar (built-in lists + areas
with nested projects and progress rings) and a main panel that shows the selected
list grouped by project (or by heading inside a project). Light/dark toggle.

Reads go through the same read-only, lock-tolerant layer as the MCP tools.

Two ways to run:
  - `suur-things-mcp dashboard`  → foreground (CLI), opens your browser
  - the `open_dashboard` MCP tool → background daemon thread, returns the URL

The background path uses a module-level singleton so repeated calls return the
already-running URL instead of binding a second port.
"""

from __future__ import annotations

import socket
import subprocess
import threading
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from . import reads

DEFAULT_PORT = 8765

# Singleton state for the background (MCP tool) server.
_running: dict[str, Any] = {}


# --- App ------------------------------------------------------------------

async def _index(_request: Request) -> HTMLResponse:
    return HTMLResponse(INDEX_HTML)


async def _state(_request: Request) -> JSONResponse:
    """Board data (legacy). Tolerates a busy DB: serve an error payload, never 500."""
    try:
        return JSONResponse({"ok": True, "board": reads.board()})
    except Exception as exc:  # noqa: BLE001 - dashboard must stay up
        return JSONResponse({"ok": False, "error": str(exc), "board": {}})


async def _sidebar(_request: Request) -> JSONResponse:
    """The navigation tree: built-in lists + areas with nested projects."""
    try:
        return JSONResponse({"ok": True, "sidebar": reads.sidebar()})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc), "sidebar": {}})


async def _items(request: Request) -> JSONResponse:
    """To-dos for a selected list/area/project (?id=...)."""
    list_id = request.query_params.get("id", "today")
    try:
        return JSONResponse({"ok": True, **reads.list_items(list_id)})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc), "items": []})


def create_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/", _index),
            Route("/api/state", _state),
            Route("/api/sidebar", _sidebar),
            Route("/api/items", _items),
        ]
    )


# --- Server lifecycle -----------------------------------------------------

def _pick_port(preferred: int = DEFAULT_PORT) -> int:
    """Return the preferred port if free, otherwise an OS-assigned free port."""
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
    """Start the dashboard in a daemon thread (idempotent). Returns its URL.

    Daemon thread so it never blocks the MCP stdio loop and dies with the host.
    """
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
        except Exception:  # noqa: BLE001 - opening a browser is best-effort
            pass
    return url


def serve_foreground(port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
    """Blocking server for the `dashboard` CLI subcommand."""
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
    --red:#e0402b; --check-border:#c2c6cc; --header-rule:#ececee;
  }
  html[data-theme="dark"] {
    --side-bg:#23272c; --main-bg:#1b1e23; --text:#e7e9ec; --muted:#888e97;
    --divider:#31363c; --row-hover:#2b3035; --row-sel:#384049; --accent:#4c8dff;
    --pill-border:#474d55; --ring-bg:#3a3f46; --ring-fg:#888e97; --badge:#363b42;
    --red:#ff6453; --check-border:#5a6068; --header-rule:#2e333a;
  }
  * { box-sizing:border-box; }
  html, body { height:100%; margin:0; overflow:hidden; }
  body { display:flex; font:14px/1.45 -apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif;
    background:var(--main-bg); color:var(--text); -webkit-font-smoothing:antialiased; }

  /* Sidebar */
  .sidebar { width:272px; flex:0 0 272px; background:var(--side-bg); height:100vh;
    overflow-y:auto; padding:14px 10px 20px; border-right:1px solid var(--divider); }
  .nav-item { display:flex; align-items:center; gap:9px; padding:6px 10px; margin:1px 0;
    border-radius:7px; cursor:pointer; white-space:nowrap; user-select:none; }
  .nav-item:hover { background:var(--row-hover); }
  .nav-item.active { background:var(--row-sel); }
  .nav-item .ico { width:18px; text-align:center; flex:0 0 18px; font-size:14px; }
  .nav-item .label { flex:1; overflow:hidden; text-overflow:ellipsis; }
  .nav-item .count { color:var(--muted); font-size:12.5px; font-variant-numeric:tabular-nums; }
  .nav-sep { height:14px; }
  .area-head { padding:7px 10px 3px; margin-top:8px; font-weight:600; font-size:13.5px;
    display:flex; align-items:center; gap:8px; white-space:nowrap; cursor:pointer; border-radius:7px; }
  .area-head:hover { background:var(--row-hover); }
  .area-head.active { background:var(--row-sel); }
  .area-head .stack { color:var(--muted); font-size:12px; }
  .project { padding:5px 10px 5px 14px; margin:1px 0; border-radius:7px; cursor:pointer;
    display:flex; align-items:center; gap:9px; white-space:nowrap; }
  .project:hover { background:var(--row-hover); }
  .project.active { background:var(--row-sel); }
  .project .label { flex:1; overflow:hidden; text-overflow:ellipsis; }
  svg.ring { flex:0 0 16px; }
  .ring-bg { fill:none; stroke:var(--ring-bg); stroke-width:2; }
  .ring-fg { fill:none; stroke:var(--ring-fg); stroke-width:2; stroke-linecap:round; }
  .ring-dot { fill:var(--ring-fg); }

  /* Main */
  .main { flex:1; height:100vh; overflow-y:auto; padding:30px 40px 80px; position:relative; min-width:0; }
  .main-head { display:flex; align-items:center; gap:11px; margin-bottom:22px; }
  .main-head .ico { font-size:24px; }
  .main-head h1 { font-size:23px; font-weight:700; margin:0; }
  .theme-btn { position:fixed; top:16px; right:20px; z-index:5; border:1px solid var(--divider);
    background:var(--main-bg); color:var(--text); width:30px; height:30px; border-radius:8px;
    cursor:pointer; font-size:15px; display:flex; align-items:center; justify-content:center; }
  .theme-btn:hover { background:var(--row-hover); }

  .group-head { display:flex; align-items:center; gap:8px; font-weight:600; font-size:14.5px;
    padding:18px 0 7px; border-bottom:1px solid var(--header-rule); margin-bottom:4px; }
  .row { display:flex; align-items:center; gap:11px; padding:6px 8px; border-radius:7px;
    cursor:pointer; max-width:760px; }
  .row:hover { background:var(--row-hover); }
  .box { width:17px; height:17px; flex:0 0 17px; border:1.5px solid var(--check-border);
    border-radius:5px; display:flex; align-items:center; justify-content:center; }
  .box.done { background:var(--accent); border-color:var(--accent); }
  .box.done::after { content:"✓"; color:#fff; font-size:11px; font-weight:700; }
  .box.cancel { background:var(--muted); border-color:var(--muted); }
  .box.cancel::after { content:"✕"; color:#fff; font-size:10px; font-weight:700; }
  .row .title { flex:1 1 auto; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .row.is-done .title { color:var(--muted); }
  .meta { display:flex; align-items:center; gap:6px; flex:0 0 auto; }
  .pill { font-size:11.5px; padding:1px 8px; border:1px solid var(--pill-border); color:var(--muted);
    border-radius:11px; white-space:nowrap; }
  .note-ico { color:var(--muted); font-size:12px; }
  .due { display:inline-flex; align-items:center; gap:4px; color:var(--red); font-size:12px; white-space:nowrap; }
  .due .dot { width:9px; height:9px; border-radius:50%; background:var(--red); display:inline-block; }
  .empty, .err { color:var(--muted); padding:40px 4px; }
  .err { color:var(--red); }
</style>
</head>
<body>
<aside class="sidebar" id="sidebar"></aside>
<main class="main">
  <button class="theme-btn" id="theme" title="Toggle light/dark">◐</button>
  <div class="main-head"><span class="ico" id="head-ico">⭐</span><h1 id="head-title">Today</h1></div>
  <div id="content"></div>
</main>
<script>
const $ = (s, r=document) => r.querySelector(s);
let SEL = {id:"today", icon:"⭐", title:"Today", kind:"builtin"};

// --- theme ---
function applyTheme(t){ document.documentElement.setAttribute("data-theme", t);
  $("#theme").textContent = t === "dark" ? "☀" : "☾"; localStorage.setItem("things-theme", t); }
applyTheme(localStorage.getItem("things-theme") ||
  (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
$("#theme").onclick = () => applyTheme(
  document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark");

// --- progress ring ---
function ring(p){
  const r=6, c=2*Math.PI*r, off=c*(1-p);
  if (p <= 0) return `<svg class="ring" width="16" height="16" viewBox="0 0 16 16"><circle class="ring-bg" cx="8" cy="8" r="6"/></svg>`;
  return `<svg class="ring" width="16" height="16" viewBox="0 0 16 16">`+
    `<circle class="ring-bg" cx="8" cy="8" r="6"/>`+
    `<circle class="ring-fg" cx="8" cy="8" r="6" stroke-dasharray="${c.toFixed(2)}" `+
    `stroke-dashoffset="${off.toFixed(2)}" transform="rotate(-90 8 8)"/></svg>`;
}

// --- sidebar ---
async function loadSidebar(){
  const data = await (await fetch("/api/sidebar")).json();
  const el = $("#sidebar"); el.innerHTML = "";
  if (!data.ok){ el.innerHTML = `<div class="err">${data.error||"error"}</div>`; return; }
  const sb = data.sidebar;

  for (const b of sb.builtins){
    const row = document.createElement("div");
    row.className = "nav-item"; row.dataset.id = b.id;
    row.innerHTML = `<span class="ico">${b.icon}</span><span class="label">${esc(b.title)}</span>`+
      (b.count != null ? `<span class="count">${b.count}</span>` : "");
    row.onclick = () => select({id:b.id, icon:b.icon, title:b.title, kind:"builtin"});
    el.appendChild(row);
  }
  el.appendChild(divEl("nav-sep"));

  const areas = sb.areas.concat(sb.arealess.length ? [{uuid:null, title:"Projects", projects:sb.arealess}] : []);
  for (const a of areas){
    const head = document.createElement("div");
    head.className = "area-head"; if (a.uuid) head.dataset.id = a.uuid;
    head.innerHTML = `<span class="stack">▥</span><span class="label">${esc(a.title)}</span>`;
    if (a.uuid) head.onclick = () => select({id:a.uuid, icon:"▥", title:a.title, kind:"area"});
    el.appendChild(head);
    for (const p of a.projects){
      const row = document.createElement("div");
      row.className = "project"; row.dataset.id = p.uuid;
      row.innerHTML = `${ring(p.progress)}<span class="label">${esc(p.title)}</span>`;
      row.onclick = () => select({id:p.uuid, icon:ringIcon(p.progress), title:p.title, kind:"project"});
      el.appendChild(row);
    }
  }
}
function ringIcon(){ return "◔"; }
function divEl(c){ const d=document.createElement("div"); d.className=c; return d; }

// --- selection + main panel ---
function setActive(id){
  document.querySelectorAll(".nav-item,.area-head,.project").forEach(n => {
    n.classList.toggle("active", n.dataset.id === String(id));
  });
}
async function select(sel){
  SEL = sel; setActive(sel.id);
  $("#head-ico").textContent = sel.kind === "project" ? "" : sel.icon;
  $("#head-title").textContent = sel.title;
  const c = $("#content"); c.innerHTML = `<div class="empty">loading…</div>`;
  const data = await (await fetch("/api/items?id=" + encodeURIComponent(sel.id))).json();
  if (!data.ok){ c.innerHTML = `<div class="err">${data.error||"error"}</div>`; return; }
  render(data.items, data.kind);
}

function groupBy(items, key){
  const groups = [], idx = {};
  for (const it of items){
    const k = it[key] || "\\u0000";
    if (!(k in idx)){ idx[k] = groups.length; groups.push({key: it[key]||null, items:[]}); }
    groups[idx[k]].items.push(it);
  }
  return groups;
}

function render(items, kind){
  const c = $("#content"); c.innerHTML = "";
  if (!items.length){ c.innerHTML = `<div class="empty">Nothing here.</div>`; return; }
  const groupKey = kind === "project" ? "heading_title" : "project_title";
  // Loose items (no project/heading) render first, ungrouped, like Things.
  const groups = groupBy(items, groupKey).sort((a,b) => (a.key?1:0) - (b.key?1:0));
  for (const g of groups){
    if (g.key){
      const h = document.createElement("div");
      h.className = "group-head"; h.textContent = g.key;
      c.appendChild(h);
    }
    for (const it of g.items) c.appendChild(rowEl(it));
  }
}

function rowEl(it){
  const done = it.status === "completed", cancel = it.status === "canceled";
  const row = document.createElement("div");
  row.className = "row" + (done||cancel ? " is-done" : "");
  row.onclick = () => { window.location.href = "things:///show?id=" + encodeURIComponent(it.uuid); };

  const box = `<span class="box ${done?"done":cancel?"cancel":""}"></span>`;
  let meta = "";
  if (it.has_notes) meta += `<span class="note-ico">📄</span>`;
  (it.tags || []).forEach(t => meta += `<span class="pill">${esc(t)}</span>`);
  if (it.deadline){
    const overdue = it.deadline < new Date().toISOString().slice(0,10);
    meta += `<span class="due">${overdue?'<span class="dot"></span>':"⚑"} ${it.deadline}</span>`;
  }
  row.innerHTML = `${box}<span class="title">${esc(it.title||"(untitled)")}</span>`+
    (meta ? `<span class="meta">${meta}</span>` : "");
  return row;
}

function esc(s){ return String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }

// --- boot ---
loadSidebar().then(() => select(SEL));
</script>
</body>
</html>
"""
