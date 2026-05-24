# Roadmap

The thesis for v2: v1 treats Things as a database (CRUD). v2 treats Things as the
**memory and spec layer for an AI coding agent** — pull the task manager *inside* the
plan → code → ship loop, and give humans a board to glance at.

Architecture principle: **the server stays dumb.** It returns clean structured data
and ships packaged MCP **prompts**. The judgment (prioritize, triage, synthesize a
review) lives in the agent, not a hardcoded rules engine. Reads stay on SQLite,
writes stay on the URL Scheme.

## Phase 1 — Foundation ✅ (shipped)

- **`overview` tool** — one cheap call returns a whole-system digest: counts per
  list, today's items, overdue, projects with no open next action, recent
  completions. Replaces ~10 read calls.
- **Read-only Things-style dashboard** — two-pane web UI: sidebar (lists + areas
  with nested projects and progress rings) and a main panel grouped by
  project/heading. Light/dark toggle. Cards deep-link into Things. Run via the
  `open_dashboard` tool or `suur-things-mcp dashboard`. Reuses the read layer; no
  new heavy deps (starlette + uvicorn already in the tree).
- **`plan_to_project` prompt** — hand it an implementation plan; the agent uses the
  `batch` tool to materialize a Things project (headings per phase, to-dos per step,
  checklist items per sub-task).

## Phase 2 — GTD copilot (prompts only, no new tools)

- **`weekly-review`** — agent flags projects with no next action, Someday items
  rotting for N+ days, overdue deadlines, quiet areas; proposes fixes; applies on
  approval.
- **`triage-inbox`** — agent proposes project/area + tags + `when` per Inbox item
  with reasoning; batch-applies on approval.
- **`whats-next`** — ranks Today/Anytime by deadline, age, tags; recommends the next
  task to work on.
- **`standup`** — yesterday's logbook + today + blocked, formatted to paste into
  Slack or a PR description.
- **Code recipes** (README + optional prompts) — `capture-todos` (sweep
  TODO/FIXME into Things with `file:line` + SHA) and `close-from-commit`
  (complete tasks referenced by a merged commit). Delivered as agent guidance, not
  tools — the agent already has Grep/Bash/git.

## Phase 3 — Live board + light writes (stretch)

- Dashboard auto-refresh (poll or SSE).
- Drag a card between columns to reschedule → fires `things:///update?...&when=`
  via the existing write path (requires `THINGS_AUTH_TOKEN`). First write-capable
  surface in the dashboard, explicitly opt-in.

---

Full design rationale, premises, and open questions live in the office-hours design
doc that produced this roadmap.
