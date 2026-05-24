"""Read-only Kanban dashboard for Things.

A tiny Starlette app served by uvicorn. Columns are the Things lists; cards
deep-link back into Things via the URL Scheme. Reads go through the same
read-only, lock-tolerant layer as the MCP tools.

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
    """Board data. Tolerates a busy DB: serve an error payload, never 500."""
    try:
        return JSONResponse({"ok": True, "board": reads.board()})
    except Exception as exc:  # noqa: BLE001 - dashboard must stay up
        return JSONResponse({"ok": False, "error": str(exc), "board": {}})


def create_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/", _index),
            Route("/api/state", _state),
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
<title>Things Board</title>
<style>
  :root {
    --bg: #f4f5f7; --col: #ebecf0; --card: #fff; --text: #172b4d;
    --muted: #6b778c; --line: #dfe1e6; --accent: #2684ff; --overdue: #de350b;
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#1d2125; --col:#22272b; --card:#2c333a; --text:#e6edf3;
      --muted:#9aa7b5; --line:#3a434d; --accent:#579dff; --overdue:#ff6b53; }
  }
  * { box-sizing: border-box; }
  body { margin:0; font:14px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
    background:var(--bg); color:var(--text); }
  header { display:flex; align-items:center; gap:16px; padding:14px 20px;
    border-bottom:1px solid var(--line); position:sticky; top:0; background:var(--bg); }
  header h1 { font-size:16px; margin:0; font-weight:600; }
  header .meta { color:var(--muted); font-size:12px; }
  button { font:inherit; color:var(--text); background:var(--card); border:1px solid var(--line);
    border-radius:6px; padding:5px 12px; cursor:pointer; }
  button:hover { border-color:var(--accent); }
  .board { display:flex; gap:14px; padding:18px 20px; overflow-x:auto; align-items:flex-start; }
  .column { background:var(--col); border-radius:10px; min-width:280px; max-width:320px;
    flex:0 0 auto; display:flex; flex-direction:column; max-height:calc(100vh - 110px); }
  .column h2 { font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted);
    margin:0; padding:12px 14px 8px; display:flex; justify-content:space-between; }
  .cards { padding:0 8px 10px; overflow-y:auto; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:8px;
    padding:9px 11px; margin:6px 0; cursor:pointer; transition:border-color .12s; }
  .card:hover { border-color:var(--accent); }
  .card .t { font-weight:500; }
  .card .sub { color:var(--muted); font-size:12px; margin-top:3px; }
  .badges { margin-top:6px; display:flex; flex-wrap:wrap; gap:4px; }
  .badge { font-size:11px; padding:1px 7px; border-radius:10px; background:var(--col); color:var(--muted); }
  .badge.due { background:rgba(222,53,11,.12); color:var(--overdue); }
  .empty { color:var(--muted); font-size:12px; padding:6px 14px 12px; font-style:italic; }
  .err { color:var(--overdue); padding:10px 20px; }
</style>
</head>
<body>
<header>
  <h1>📋 Things Board</h1>
  <span class="meta" id="meta">loading…</span>
  <button id="refresh" style="margin-left:auto">Refresh</button>
</header>
<div id="err" class="err" hidden></div>
<div class="board" id="board"></div>
<script>
const COLS = [["inbox","Inbox"],["today","Today"],["upcoming","Upcoming"],["anytime","Anytime"],["someday","Someday"]];
const todayStr = new Date().toISOString().slice(0,10);

function card(item) {
  const el = document.createElement("div");
  el.className = "card";
  el.onclick = () => { window.location.href = "things:///show?id=" + encodeURIComponent(item.uuid); };
  const t = document.createElement("div"); t.className = "t"; t.textContent = item.title || "(untitled)";
  el.appendChild(t);
  const ctx = item.project_title || item.area_title;
  if (ctx) { const s = document.createElement("div"); s.className="sub"; s.textContent = ctx; el.appendChild(s); }
  const badges = document.createElement("div"); badges.className = "badges";
  if (item.deadline) {
    const b = document.createElement("span");
    b.className = "badge" + (item.deadline < todayStr ? " due" : "");
    b.textContent = "⚑ " + item.deadline; badges.appendChild(b);
  }
  (item.tags || []).forEach(tag => {
    const b = document.createElement("span"); b.className="badge"; b.textContent = tag; badges.appendChild(b);
  });
  if (badges.children.length) el.appendChild(badges);
  return el;
}

async function load() {
  try {
    const r = await fetch("/api/state");
    const data = await r.json();
    const errEl = document.getElementById("err");
    if (!data.ok) { errEl.hidden=false; errEl.textContent = "Could not read Things: " + (data.error||""); return; }
    errEl.hidden = true;
    const board = document.getElementById("board"); board.innerHTML = "";
    let total = 0;
    for (const [key,label] of COLS) {
      const items = data.board[key] || []; total += items.length;
      const col = document.createElement("div"); col.className = "column";
      const h = document.createElement("h2"); h.innerHTML = `<span>${label}</span><span>${items.length}</span>`;
      col.appendChild(h);
      const cards = document.createElement("div"); cards.className = "cards";
      if (!items.length) { const e=document.createElement("div"); e.className="empty"; e.textContent="nothing here"; cards.appendChild(e); }
      items.forEach(it => cards.appendChild(card(it)));
      col.appendChild(cards); board.appendChild(col);
    }
    document.getElementById("meta").textContent = total + " items · " + new Date().toLocaleTimeString();
  } catch (e) {
    const errEl = document.getElementById("err"); errEl.hidden=false; errEl.textContent = "Dashboard error: " + e;
  }
}
document.getElementById("refresh").onclick = load;
load();
</script>
</body>
</html>
"""
