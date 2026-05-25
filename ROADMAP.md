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
- **Dashboard** — local web UI with two views and a light/dark toggle. Run via the
  `open_dashboard` tool or `suur-things-mcp dashboard`. Reuses the read layer; no new
  heavy deps (starlette + uvicorn already in the tree).
  - **Classic**: faithful Things two-pane replica (sidebar with areas + nested
    projects + progress rings; main panel grouped by project/heading).
  - **Project boards**: saved Kanbans in the sidebar (after Today). Columns are Things
    tags; each board is named and scoped to whole areas or specific projects via a
    Notion-style ⚙ panel. Card status lives in Things, so it syncs. Multiple boards.
  - **Editing**: click any task → edit dialog; drag cards between columns. Writes go
    through the URL Scheme and require `THINGS_AUTH_TOKEN` (read-only without it).
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

## Phase 3 — Live board + writes (partially shipped)

- ✅ Dashboard writes: edit dialog + drag cards between Kanban columns (retag via
  the URL Scheme, `THINGS_AUTH_TOKEN`).
- Dashboard auto-refresh (poll or SSE) — still TODO.
- Drag in the Classic view to reschedule (`when=`) — still TODO.
- Stable dashboard port across rapid restarts (currently hops if the port is in
  TIME_WAIT) — minor.

---

Full design rationale, premises, and open questions live in the office-hours design
doc that produced this roadmap.
