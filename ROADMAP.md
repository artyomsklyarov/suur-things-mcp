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
  - **Project boards**: saved portfolio Kanbans in the sidebar (compact group after
    Today). Cards are projects/areas (overview), staged into columns by drag. Named,
    multiple, scoped to whole areas or specific projects via a Notion-style ⚙ panel.
  - **Priority Square**: Eisenhower matrix over Today; drag tasks into quadrants.
  - Stage placement + priority quadrants are browser overlays (no token to drag);
    current view is preserved on refresh (URL hash).
  - **Editing**: click any task → edit dialog; drag cards between columns. Writes go
    through the URL Scheme and require `THINGS_AUTH_TOKEN` (read-only without it).
- **`plan_to_project` prompt** — hand it an implementation plan; the agent uses the
  `batch` tool to materialize a Things project (headings per phase, to-dos per step,
  checklist items per sub-task).

## Repo linking ✅ (Phase 1 shipped)

Connect a Things project/area to one or more local git repos (e.g. an app + its
website). The link lives in the browser config (`links: {itemUuid: {kind, repos:[
{repo, github, label}]}}`), never written to Things.

- **Tools**: `link_repo`, `unlink_repo`, `list_links`, `current_link(cwd)`.
- **`work_on_repo` prompt** (`/mcp__suurthings__work_on_repo`) — the agent passes its cwd, `current_link`
  resolves it to the linked project/area, returns the open tasks, and the agent
  works them. cwd resolves via `cwd` arg → `CLAUDE_PROJECT_DIR` → `getcwd()` (never
  trusts the bare server cwd under uvx).
- **Dashboard**: per-card repo chips with Open-in-editor / Open-on-GitHub, plus a
  🔗 to link more. `/api/open` takes only an item_id + index (server-side lookup +
  validation); an `Origin`/`Sec-Fetch-Site` guard now protects all write endpoints.
- **Phase 2 ✅ (shipped)**: `repo_to_issue` + `issues_to_todos` prompts
  (agent runs `gh`; server never bundles it).

## Auto-organize folder ✅ (shipped)

A ✨ button on any folder (project / area / Inbox) that enriches its tasks with the
help of your own agent, reviewed before anything is written.

- **`organize_folder` prompt** (`/mcp__suurthings__organize_folder`) — agent-side: read folder, propose clearer
  titles + notes + tags (reusing existing tags), review in chat, apply on approval.
- **Dashboard button** — spawns your installed agent **headlessly with no tools and
  no MCP** (`claude -p --strict-mcp-config --mcp-config '{}' --allowedTools "" --model
  sonnet`), so it can only PROPOSE — it physically can't write or be injected into
  writing. Background job (dedupe + single-run cap + 180s timeout); suggestions shown
  in a per-field review modal; Apply writes additively (title replace, **append-notes**,
  **add-tags** — never overwrites). No LLM/API key in the server; uses your agent's auth.
- Configure the agent/model via `prefs.agent` / `prefs.agent_model` (or
  `SUUR_THINGS_AGENT`). Needs `THINGS_AUTH_TOKEN` to apply.

## Phase 2 — GTD copilot ✅ (shipped — prompts only, no new tools)

- ✅ **`weekly_review`** — flags projects with no next action, Someday items rotting
  for N+ days, overdue deadlines, quiet/overloaded areas; proposes fixes; applies on
  approval.
- ✅ **`triage_inbox`** — proposes project/area + tags + `when` per Inbox item; files
  on approval (moves via `update_todo(list_id=…)`).
- ✅ **`whats_next`** — ranks Today/Anytime by deadline, age, tags; recommends the
  single next task plus runners-up.
- ✅ **`standup`** — yesterday's logbook + today + blocked, formatted to paste into
  Slack or a PR description.
- ✅ **Code recipes** — shipped as the `capture_todos` (sweep TODO/FIXME into Things
  with `file:line`) and `close_from_commit` (complete tasks referenced by a commit)
  prompts. The agent already has Grep/Bash/git; the server adds no tools.

## Phase 3 — Live board + writes ✅ (shipped)

- ✅ Dashboard task edit dialog (Things-style card; writes via URL Scheme,
  `THINGS_AUTH_TOKEN`; saves on close only if changed). Board/priority dragging uses
  browser overlays — no token needed.
- ✅ Dashboard auto-refresh (25s poll; pauses during edit/drag/filter/search and in
  background tabs; preserves scroll position).
- ✅ Drag a task onto **Today / Anytime / Someday** in the sidebar to reschedule (`when=`).
- ✅ Stable dashboard port — reuses a live instance and rebinds 8765 through TIME_WAIT
  (`SO_REUSEADDR`); only falls back to a random port if a *foreign* process holds it.

## Dashboard affordances ✅ (shipped)

The "few modern affordances Things is missing," layered on as browser overlays:

- ✅ **Image attachments** — drag/paste/pick an image on a task; bytes live on disk under
  the config dir, only metadata in `board.json`. With a token, a `file://` reference is
  appended to the task's notes so the Things app shows it too. `attach_image` MCP tool +
  `/api/attach|attachment|detach` endpoints (serve is overlay-gated, no arbitrary reads).
- ✅ **Priority Levels** — a 2×2 P1–P4 view ranked from your *existing* Things tags (not a
  separate overlay). Map tags → levels in a ⚙ editor; drag a task between levels and the
  mapped tag is rewritten in Things. Works over Today and as a per-list/area/project view.
- ✅ **Area roll-up** — an area view folds in its projects' tasks, grouped by project. A
  per-area header toggle turns it off; the choice persists in `board.json` (`area_prefs`).
- ✅ **App-window mode** — `dashboard --app` (or `open_dashboard(app=true)`) opens the board
  in a frameless Chromium window (no tabs/address bar), falling back to a normal tab.

---

Full design rationale, premises, and open questions live in the office-hours design
doc that produced this roadmap.
