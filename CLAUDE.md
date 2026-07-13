# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An MCP server for Things 3 (Cultured Code) on macOS, plus a local web dashboard. Python ≥3.10, managed with `uv`, published to PyPI as `suur-things-mcp`.

## Commands

```bash
uv sync --dev                          # install deps (dev group included)
uv run pytest                          # all tests — safe anywhere, never touches the real Things DB
uv run pytest tests/test_urlscheme.py::test_name   # single test
uv run pytest -m browser               # real-Chromium tests of the embedded dashboard JS
uv run playwright install chromium     # one-time, required before browser tests run (they skip otherwise)
uv run suur-things-mcp                 # run the MCP server over stdio
uv run suur-things-mcp dashboard       # run the dashboard (add --app for app window, --no-open for headless service)
```

Data-route tests skip automatically when Things isn't installed (CI runs on Linux); URL-building and dashboard-route tests run everywhere.

The dashboard may already be running on port 8765 as a launchd KeepAlive service (`dashboard --install-service`). Never start a competing foreground instance on that port — `ensure_running` reuses a live instance, and a port conflict causes a browser-open loop. Tests already pick random free ports.

## The core invariant

**Reads come from the local SQLite database (read-only); writes go *only* through the official Things URL Scheme (`things:///` URLs fired via `open -g`).** Cultured Code states that writing to the Things DB directly can corrupt it. Never open the DB writable, never add a write path that bypasses `urlscheme.py`. `reads.py` opens the DB with `mode=ro&immutable=1`.

## Architecture

Five modules in `src/suur_things_mcp/`:

- **`server.py`** — the FastMCP server: ~31 `@mcp.tool()` definitions (thin wrappers over `reads`/`urlscheme`/`config`) and ~12 `@mcp.prompt()` packaged workflows. `main()` dispatches the `dashboard` subcommand; otherwise runs stdio MCP. The server deliberately stays "dumb": it returns structured data and ships prompts; judgment lives in the connected agent.
- **`reads.py`** — all DB reads via the `things.py` library, plus dashboard-shaped aggregations (`sidebar`, `list_items`, `board_cards`, `overview`).
- **`urlscheme.py`** — builds, encodes, and executes `things:///` URLs. Injects the auth token where required (`AUTH_REQUIRED` set; the `json` batch command decides dynamically) and **redacts the token from every returned URL and error message**. Keep it that way.
- **`dashboard.py`** — a single self-contained Starlette app. API routes and server logic occupy roughly the first 775 lines; **the entire frontend (HTML/CSS/JS) is one embedded string, `INDEX_HTML`, from ~line 776 to the end** — no build step, no external JS, no framework. Binds 127.0.0.1 only.
- **`config.py`** — persistence for the dashboard *overlay* in `~/.config/suur-things-mcp/board.json`: boards, Eisenhower priorities, priority-level tag maps, time-blocks, repo links, prefs, attachment metadata, and the auth-token file. Every section has a `_clean_*` sanitizer that tolerates junk input; new config sections should follow that pattern.
- **`organize.py`** — spawns the user's own agent CLI (`claude`/`codex`) headlessly to propose Inbox triage. The subprocess gets **no tools, no MCP, and an environment stripped of `THINGS_AUTH_TOKEN`** — it can only propose text; the user reviews before anything is written. Preserve that sandbox.

### The overlay concept

Boards, quadrant/priority placement, time-blocks, and repo links are dashboard-side concepts Things doesn't have. They live in `board.json`, keyed by stable Things UUIDs, and are **never written to Things** — which is why dragging needs no auth token, while editing a task's real fields (title/when/tags/…) goes through the URL Scheme and does.

### Auth model

Reads and *creating* new items need no token. *Modifying* existing items needs `THINGS_AUTH_TOKEN` (env var, or `~/.config/suur-things-mcp/token`, resolved by `config.auth_token()`). Without it, dashboard edit UI is read-only and update tools raise a helpful error.

### Dashboard security (preserve when touching dashboard.py)

- 127.0.0.1 binding + `TrustedHostMiddleware` (host allowlist) blocks DNS rebinding.
- `_OriginGuard` rejects POSTs whose full origin (scheme+host+**port**) isn't the server's own, and rejects `sec-fetch-site` ≠ `same-origin` — a page on another localhost port must not be able to drive the API.
- Version string is injected into the page via `json.dumps` so it can't break out of the JS literal.

## Testing the embedded frontend

There is no JS test runner. Two mechanisms cover the embedded JS instead:

1. **Source-string assertions** in `tests/test_dashboard.py` (e.g. `"let CREATING=false" in html`) guard load-bearing JS patterns like the quick-add re-entry lock. If you refactor the embedded JS, these may fail on exact strings — update them deliberately, don't delete the guards.
2. **Playwright tests** in `tests/test_dashboard_browser.py` (marker `browser`) load the real page in headless Chromium for behavior pure-Python can't reach (XSS escaping, button feedback). They boot the real app on a random port in a background uvicorn thread.

Dashboard `TestClient` instances must set `base_url="http://127.0.0.1:..."` — the default `testserver` host is rejected by the host allowlist.

## Env vars

`THINGS_AUTH_TOKEN` (write access), `THINGS_DB` (override SQLite path — point at a backup for testing), `SUUR_THINGS_CONFIG` (override board.json path), `SUUR_THINGS_EDITOR` / `SUUR_THINGS_TERMINAL` (repo-launch buttons), `SUUR_THINGS_AGENT` (which CLI ✨ organize spawns).

## Releasing

The version lives in **two places that must stay in sync**: `pyproject.toml` and `src/suur_things_mcp/__init__.py` (`__version__` drives the dashboard's auto-reload-on-upgrade). Update `CHANGELOG.md` (Keep a Changelog format). Publishing a GitHub Release triggers `release.yml`, which builds with `uv build` and publishes to PyPI via Trusted Publishing. Commit style for releases: `v0.8.6 — short description (#PR)`.

## Known URL Scheme limits (not bugs)

- Creating headings isn't supported — only the app can.
- Create commands don't return the new item's UUID; search for it afterward (`reads.find_by_exact_title` exists for this).
- macOS only.
