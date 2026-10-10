# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current handoff

Read root CONTEXT.MD (product), SPEC.MD (technical), STATUS.MD (verified state), TODO.MD (owner actions) and PLAN.MD (unfinished work). The .autoloop documents are historical improvement evidence; its completed epics are enabled. Current explicit release authorization supersedes that run's no-publish/preserve-uncommitted boundary, without authorizing real task writes or live paid models.

## What this is

An MCP server for Things 3 (Cultured Code) on macOS, plus a local web dashboard. Python ≥3.10, managed with `uv`, published to PyPI as `suur-things-mcp`.

## Commands

```bash
uv sync --dev                          # install deps (dev group included)
uv run pytest                          # all tests — safe anywhere, never touches the real Things DB
uv run pytest tests/test_urlscheme.py::test_name   # single test
uv run pytest -m browser               # real-Chromium tests of the dashboard's JS
uv run playwright install chromium     # one-time, required before browser tests run (they skip otherwise)
uv run ruff check .                    # CI gate — lint must pass
uv run suur-things-mcp                 # run the MCP server over stdio
uv run suur-things-mcp dashboard       # run the dashboard (--app for an app window, --no-open for headless service)
```

`dashboard --install-service` / `--uninstall-service` manage a launchd KeepAlive LaunchAgent (`io.suur.things-dashboard`) that runs `dashboard --no-open` at login.

The dashboard may already be running on port 8765 as that service. Never start a competing foreground instance on that port — `ensure_running`/`serve_foreground` reuse a live instance, and a port conflict causes a browser-open loop. Tests already pick random free ports.

## The core invariant

**Reads come from the local SQLite database (read-only); writes go *only* through the official Things URL Scheme (`things:///` URLs fired via `open -g`).** Cultured Code states that writing to the Things DB directly can corrupt it. Never open the DB writable, never add a write path that bypasses `urlscheme.py`. `reads._db_uri()` builds `mode=ro` (`&immutable=1` for stable count snapshots) URIs.

## Architecture

Six modules in `src/suur_things_mcp/`, plus the frontend as package data:

- **`server.py`** — the FastMCP server: ~32 `@mcp.tool()` definitions (thin wrappers over `reads`/`urlscheme`/`config`) and ~13 `@mcp.prompt()` packaged workflows. `main()` dispatches the `dashboard` subcommand (hand-rolled argv parsing, no argparse); otherwise runs stdio MCP. The server deliberately stays "dumb": it returns structured data and ships prompts; judgment lives in the connected agent.
- **`reads.py`** — all DB reads via the `things.py` library, plus dashboard-shaped aggregations (`sidebar`, `list_items`, `board_cards`, `overview`, `item_detail`) and `stale_cohorts()` for backlog review. List-returning tools project through `_card()` for a compact token budget — keep it cheap: it carries `age_days`/`idle_days` as ints, never the raw timestamps.
- **`urlscheme.py`** — builds, encodes, and executes `things:///` URLs. Injects the auth token where required (`AUTH_REQUIRED` set; the `json` batch command decides dynamically via `requires_auth=`) and **redacts the token from every returned URL and error message**. Keep it that way.
- **`dashboard.py`** — a single self-contained Starlette app (~900 lines, all Python): API routes, security middleware, uvicorn lifecycle, and the launchd service installer. Binds 127.0.0.1 only.
- **`static/index.html`** — **the entire frontend** (HTML + CSS + JS, ~2.1k lines) in one file. No build step, no external assets, no framework. `dashboard._index_html()` reads it from package data *per request*, so a frontend edit is live on the next browser reload (Python edits still need a server restart).
- **`config.py`** — persistence for the dashboard *overlay* in `~/.config/suur-things-mcp/board.json`: boards, Eisenhower priorities, priority-level tag maps, time-blocks, repo links, prefs, attachment metadata, and the auth-token file. Every section has a `_clean_*` sanitizer that tolerates junk input; new config sections should follow that pattern.
- **`organize.py`** — spawns the user's own agent CLI (`claude`/`codex`) headlessly to propose Inbox triage. The subprocess gets **no tools, no MCP** (Claude: `--strict-mcp-config` + empty `--mcp-config`/`--allowedTools`; Codex: `--sandbox read-only`), an environment stripped of `THINGS_AUTH_TOKEN` and unrelated secret-shaped vars (`_SENSITIVE_ENV`), while `_KEEP_ENV` retains provider authentication/base-URL variables, and an empty temp cwd. The organizer expects proposal text; Claude disables tools/MCP and Codex uses a best-effort read-only sandbox, not equivalent guarantees. The user reviews before task changes. Preserve these restrictions.

### The overlay concept

Boards, quadrant/priority placement, time-blocks, repo links, and image attachments are dashboard-side concepts Things doesn't have. They live in `board.json`, keyed by stable Things UUIDs, and are **never written to Things** — which is why dragging needs no auth token, while editing a task's real fields (title/when/tags/…) goes through the URL Scheme and does. (Priority *Levels* are the exception: they're backed by real Things tags, so dragging there does write.)

### Auth model

Reads and *creating* new items need no token. *Modifying* existing items needs `THINGS_AUTH_TOKEN` (env var, or `~/.config/suur-things-mcp/token`, resolved by `config.auth_token()`). Without it, dashboard edit UI is read-only and update tools raise a helpful error.

### Write verification (preserve in new write tools)

The URL Scheme is fire-and-forget: Things silently no-ops an unknown UUID and silently drops unknown tags. So update-style tools first reject a UUID that verifiably doesn't exist (`_item_missing`), then confirm the write landed by polling the item's `modified` stamp (`_modified_stamp`) and return `applied: true/false` plus `warning_unverified`. Tag-taking tools warn about tags Things doesn't have. Don't add a write tool that reports success it hasn't checked.

### Dashboard security (preserve when touching dashboard.py)

- 127.0.0.1 binding + `TrustedHostMiddleware` (host allowlist, outermost) blocks DNS rebinding.
- `_OriginGuard` rejects POSTs whose full origin (scheme+host+**port**) isn't the server's own, and rejects `sec-fetch-site` ≠ `same-origin` — a page on another localhost port must not be able to drive the API. Both headers absent = non-browser local client, allowed.
- **CSP is nonce-only for scripts.** `_index()` generates a per-request nonce, substitutes `__CSP_NONCE__`, and sends `script-src 'nonce-…'`. Consequence for frontend work: **an inline `on*` attribute anywhere in `index.html` will silently never fire.** Bind handlers in JS instead — static markup wires up in `wireStatic()`; dynamically built nodes get `el.onclick=`/`addEventListener` after creation.
- All untrusted text goes through `esc()` before `innerHTML`. Task titles/notes are semi-attacker-controllable (Mail to Things, agent-created tasks); CSP is the backstop, not the first line.
- The version string is injected by replacing the *quoted* `"__SUUR_VERSION__"` marker with `json.dumps(__version__)`, so it can't break out of the JS literal.
- `/api/attachment` rebuilds the path server-side from stored metadata and `resolve()`-checks it stays under the attachments dir — the request never supplies a path.

## Testing the frontend

There is no JS test runner. Two mechanisms cover the frontend instead:

1. **Source-string assertions** in `tests/test_dashboard.py` fetch `/` and assert on the served HTML (e.g. `"let CREATING=false" in html`), guarding load-bearing patterns: the quick-add re-entry lock, optimistic-checkoff revert, cursor-poll short-circuit, motion tokens, reduced-motion support. If you refactor `static/index.html`, these may fail on exact strings — update them deliberately, don't delete the guards.
2. **Playwright tests** in `tests/test_dashboard_browser.py` (marker `browser`) load the real page in headless Chromium for behavior pure-Python can't reach (XSS escaping, button feedback). They boot the real app on a random port in a background uvicorn thread.

`tests/conftest.py` builds a throwaway SQLite DB from the real Things schema (`tests/things_schema.sql`) with a known fixture dataset and points `reads` at it via the `things_db` fixture. **Don't add rows to `FIXTURE_TASKS`** — several tests assert exact set equality against it, so an extra row silently weakens all of them; add an opt-in fixture instead, the way `stale_db`/`STALE_TASKS` do for the staleness cohorts. That's what lets `reads.py` and the MCP tool layer be tested in CI on Linux — prefer it over gating a new test on a real Things install. `tests/test_server_tools.py` additionally stubs `server.execute` so no URL ever reaches a real Things app. Some `test_dashboard.py` routes still `skipif(not _things_available())`.

Dashboard `TestClient` instances must set `base_url="http://127.0.0.1:..."` — the default `testserver` host is rejected by the host allowlist.

## Env vars

`THINGS_AUTH_TOKEN` (write access), `THINGS_DB` (override SQLite path — point at a backup for testing), `SUUR_THINGS_CONFIG` (override board.json path), `SUUR_THINGS_EDITOR` / `SUUR_THINGS_TERMINAL` (repo-launch buttons), `SUUR_THINGS_AGENT` (which CLI ✨ organize spawns).

## Releasing

The version is **single-sourced in `src/suur_things_mcp/__init__.py`** (`__version__`); `pyproject.toml` declares `dynamic = ["version"]` and hatch reads it from there. Bump that one file — `__version__` also drives the dashboard's auto-reload-on-upgrade. Update `CHANGELOG.md` (Keep a Changelog format). Publishing a GitHub Release triggers `release.yml`, which builds with `uv build` and publishes to PyPI via Trusted Publishing. Commit style for releases: `v0.10.0 — short description (#PR)`.

## Known URL Scheme limits (not bugs)

- Creating headings isn't supported — only the app can.
- Create commands don't return the new item's UUID; search for it afterward (`reads.find_by_exact_title` exists for this).
- Unknown tags are silently dropped; unknown UUIDs silently no-op (hence the verification layer above).
- macOS only.

## Motion

The dashboard's motion system (tokens, reduced-motion, checkoff moment, drag feel) was designed in `plans/000`–`plans/006`, all executed. `plans/README.md` lists **deliberate non-animations** — check it before "fixing" something that doesn't animate (⌘K stays instant on purpose; the background poll never pulses the view).
