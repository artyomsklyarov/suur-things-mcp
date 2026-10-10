# Repository context

Type: Python backend/MCP server plus local macOS web dashboard. Purpose: give a user's agent structured Things 3 tasks and safe URL Scheme actions; provide familiar lists with boards, priorities, attachments and repo links. Core value: ask what to work on, then review and act on real tasks.

Stack: Python >=3.10 (unchanged), uv + hatchling, mcp/FastMCP, things.py, Starlette, uvicorn; standalone HTML/CSS/JS with package data and no frontend build. Local environment: Python 3.14.2, mcp 1.28.0, things.py 1.0.1, Starlette 1.3.1, uvicorn 0.49.0, pytest 9.1.1, Ruff 0.15.21, Playwright 1.60.0. Versions reflect the environment, not raised requirements. Current source says 0.10.0 in pre-existing uncommitted work; committed baseline is c163174 (0.9.0).

Maturity: published beta with substantial completed roadmap, recent dashboard/motion/security work and uncommitted staleness-review tooling. Architecture: reads.py reads SQLite read-only; urlscheme.py alone runs Things writes; server.py exposes MCP; dashboard.py local HTTP; config.py stores overlay JSON; organize.py proposes via user's sandboxed CLI. Preserve all boundaries. No real user data, CLI model calls, service installation or external writes during this run.

Conventions: descriptive snake_case Python, small private helpers, four spaces; compact vanilla frontend; existing tokens/theme/motion. Follow CLAUDE.md and plans/README.md. No AGENTS.md in this repository. Seven motion plans are DONE; command palette stays instant, quiet refresh never animates. Existing docs are preserved; proposed changes go to proposed-edits/.

Safety: pre-existing dirty files are listed and hashed in artifacts/preexisting-work.json. Do not edit or stage them. Stage explicit owned files only. Branch autoloop/2026-10-10; no push/release/deploy. .git mutations require approved sandbox escalation.

## Verification

Full gate: `.venv/bin/python .autoloop/scripts/verify.py <iteration-label>` (requires loopback/browser access). Runs Ruff check ., compileall src, all pytest tests against a seeded temporary Things DB and empty config/token paths, and `uv build --offline` into a temporary directory. No real Things actions: mutation tests mock execution. This eliminates all nine environment-dependent skips. Orientation: 113 passed, lint/compile/wheel/sdist pass; one existing Starlette/httpx deprecation warning. No dedicated typechecker configured: N/A. Format audit `.venv/bin/ruff format --check src tests` reports 11 existing files, intentionally advisory to avoid a broad formatting rewrite or touching dirty work.

UI: `.venv/bin/python .autoloop/scripts/capture.py <label>` serves synthetic fixture data at an ephemeral loopback port and screenshots desktop/mobile light/dark, Preferences and Trash. Read every image. Baseline report has no uncaught JS exceptions; 390px mobile main is only 118px and content is clipped. Screenshots are test data, never private task data.

## Signals of intent

ROADMAP.md phases are complete. plans/000 through 006 implemented. Source TODO/FIXME scan found no open explicit markers. Recent git history fixes quick-add and live upgrade reload. Dirty staleness work belongs to the user. New findings: config root/encoding recovery and backup uniqueness; path containment and attachment races; malformed agent suggestions; dialog focus and keyboard sidebar; dark theme UA defaults; small-window layout; frontend config/sidebar recovery; asynchronous navigation races. No new dependencies needed.
