# SUUR Things MCP

**Give any AI agent safe, structured access to your [Things 3](https://culturedcode.com/things/) tasks — plus a local, Things-faithful web dashboard with Kanban boards, an Eisenhower matrix, repo-linking, and a YouTube-thumbnail card view.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-%E2%89%A53.10-blue)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)
[![MCP](https://img.shields.io/badge/MCP-server-black)](https://modelcontextprotocol.io)

An [MCP](https://modelcontextprotocol.io) server for **Things 3** (Cultured Code) on macOS. Let Claude Code, Claude Desktop, Codex, or any MCP-capable agent read and manage your tasks, projects, and areas — and get a local dashboard that looks like Things but adds the views Things doesn't have.

```bash
# 1. point your agent at it (Claude Code shown)
claude mcp add suurthings -- uvx suur-things-mcp
# 2. (optional) open the dashboard
uvx suur-things-mcp dashboard   # → http://127.0.0.1:8765
```

That's it. Reads work immediately with no token. Add a token (below) when you want the agent to *modify* existing tasks.

---

## What it is (and the one design decision that matters)

Two data paths, deliberately split:

- **Reads** come straight from the local Things SQLite database — instant and complete: Today, Upcoming, Inbox, Anytime, Someday, Logbook, Trash, full-text search, projects, areas, tags, and full item detail.
- **Writes** go *only* through the official [Things URL Scheme](https://culturedcode.com/things/support/articles/2803573/) — add to-dos/projects, update, complete, cancel, reschedule, move between projects, append checklist items.

**Why this matters:** Cultured Code's own [AI-integration guidance](https://culturedcode.com/things/support/articles/5510170/) is blunt — *writing directly to the Things database is unsafe and can corrupt it.* They endorse the URL Scheme as the safe automation path. This server follows that exactly: it **reads** the DB read-only and **never writes** to it. Every mutation is a `things:///` URL, the same mechanism Things documents for Shortcuts and AppleScript.

So an agent can't corrupt your database through this server even if it tries. The worst a write can do is what the URL Scheme itself allows.

> **Privacy:** an agent connected to this server can read your to-do and note content, which is then sent to whatever model you're using. Review your agent's privacy policy. Nothing here phones home; there's no telemetry and no bundled LLM.

---

## ✨ Beyond Things — what the dashboard adds

`uvx suur-things-mcp dashboard` runs a local board (`127.0.0.1:8765`) that *looks* like Things but adds the views and superpowers it doesn't have. Everything here is layered **on top** — your Things data stays untouched (boards, priorities, time-blocks, and repo links live in a local overlay, never written to Things).

**Plan & focus**
- 🟦 **Priority Matrix** — an Eisenhower matrix (Do First / Schedule / Delegate / Don't Do) as a one-click view on *any* list, project, or area. Drag tasks (and an area's projects) into quadrants.
- 📅 **Daily planning / time-blocking** — a day **Timeline** view: drag today's tasks onto a 6am–11pm grid in 15/30/60-min blocks to plan the day. (Times are a private dashboard overlay.)
- 🧘 **Calm Today** — one keystroke turns an overloaded Today into a single next action plus a short list and defers the rest. AI that *subtracts* noise instead of piling on features.
- 🎯 **Calm by design** — faithful Things look, light/dark, focus-friendly; completed tasks linger checked-off until they log, like the app.

**Build & ship (for devs)**
- 🔗 **Git repo links on projects** — connect a Things project/area to one or more local repos. Cards get one-click **Open in editor (⌨) / terminal (❯) / GitHub (↗)**.
- 📊 **Repo pulse** — board cards show recent commits + open-PR count for linked repos (via `git` + `gh`).
- 🧭 **Project boards** — saved portfolio Kanbans where each card is a whole project/area (progress ring + open count), dragged across your own stage columns.

**Capture, find & tidy**
- ⌘ **Command palette (⌘K)** — jump to any list/project/board, search tasks, create, switch view, and act on a task (complete / reschedule / move) — all keyboard-only.
- ➕ **Natural-language quick-add** — type `buy milk tomorrow #errand` and it's parsed into a real to-do.
- 🧹 **Agent triage** — *Triage Inbox* (propose a home + tags + date per item) and *Organize* (tidy titles/notes/tags). Your agent proposes; you review every change before anything is written.
- 🎬 **Cards view** — a project full of links becomes a wall of **YouTube thumbnails** (a perfect "watch later").
- 🏷 **Tag filter chips** + full-text **search** across everything; inline rename, column reorder, board-card progress rings.

All of it free, local, open source — built on the safe read-SQLite / write-URL-Scheme split. No cloud, no account, no telemetry.

---

## Cool use cases — your agent + Things

These are the workflows this unlocks once an agent can see and shape your task system:

- **Plan → project, instantly.** Hand Claude an implementation plan and the `plan_to_project` prompt; it materializes a real Things project — a to-do per step with sub-tasks as checklist items — in one `batch` call. (Things' URL Scheme can't create headings, so phases get folded into titles/notes rather than faked.)
- **"What should I work on in this repo?"** Link a Things project to a local git repo. From inside that repo, the `work_on_repo` prompt resolves which project you're in (via `CLAUDE_PROJECT_DIR` / cwd), pulls its open to-dos, and works the next one.
- **Sweep code TODOs into Things.** Point your agent at the codebase: it greps `TODO`/`FIXME`, and `batch`-creates to-dos with `file:line` references — no new tool needed, the agent already has Grep + this server.
- **Auto-organize a messy Inbox.** Hit the ✨ button on any folder (or use the `organize_folder` prompt). It spawns *your* agent **headlessly with zero tools and zero MCP**, so it can only *propose* cleaner titles/notes/tags — never write or be prompt-injected. You review every change before it's applied. (And yes, an agent can re-file Inbox items into the right projects — `update` supports moving via `list-id`.)
- **Natural-language capture, for free.** Things has no NLP input — and you don't need it: tell your agent *"add buy milk tomorrow 9am #errand"* and it parses and creates it. The dashboard's ＋ also takes light shorthand (`buy milk tomorrow #errand`). Your agent is the natural-language (and recurring) layer Things lacks.
- **AI that subtracts noise.** Most todo apps win by adding features; this one makes a calm app *smarter*, not busier. `calm_today` turns an overloaded Today into one next action plus a short list; triage files your Inbox. The intelligence is for *removing* work from your face, not piling it on.
- **One-call situational awareness.** `overview` returns a whole-system digest (counts, today, overdue, projects with no next action, recent completions) in a single call instead of ten.

(The dashboard's visual features — Matrix, Timeline, Cards, boards, repo links — are in [✨ Beyond Things](#-beyond-things--what-the-dashboard-adds) above.)

---

## Requirements

- macOS with [Things 3](https://culturedcode.com/things/) installed
- [`uv`](https://docs.astral.sh/uv/) (recommended) — or any Python ≥ 3.10

## Install

`uvx` runs it with no manual install or virtualenv:

```bash
uvx suur-things-mcp            # run the MCP server over stdio
uvx suur-things-mcp dashboard  # run the dashboard instead
```

### Claude Code

```bash
# read-only (no token)
claude mcp add suurthings -- uvx suur-things-mcp

# read + write (modify existing items) — pass your token
claude mcp add suurthings --env THINGS_AUTH_TOKEN=your-token-here -- uvx suur-things-mcp
```

### Claude Desktop / Codex / other MCP clients

Add to your client's MCP config (e.g. `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "suurthings": {
      "command": "uvx",
      "args": ["suur-things-mcp"],
      "env": { "THINGS_AUTH_TOKEN": "your-token-here" }
    }
  }
}
```

`THINGS_AUTH_TOKEN` is **optional**. Without it you can read everything and *create* new to-dos/projects. It's only needed to **modify existing items**.

### Bleeding edge (straight from `main`, before a release lands on PyPI)

```bash
uvx --from git+https://github.com/artyomsklyarov/suur-things-mcp suur-things-mcp
```

## Getting your Things auth token

1. **Things → Settings → General**
2. Enable **"Enable Things URLs"**
3. Click **Manage** and copy the token

Keep it secret — it grants write access via the URL Scheme. It's stored locally (see below), never in this repo.

## Updating

There's no custom "update" command — updates ride on whatever fetched the package. `uvx` caches, so:

```bash
uvx --refresh suur-things-mcp        # re-fetch the latest release, then restart your MCP client
```

If you installed it as a persistent tool:

```bash
uv tool install suur-things-mcp      # one-time
uv tool upgrade suur-things-mcp      # update later
```

Nuclear option (clear the cache): `uv cache clean suur-things-mcp`. From `main`, add `--refresh` to the git command above.

---

## Tools (30)

### Read — no token required

| Tool | Returns |
|------|---------|
| `overview` | One-call system digest: counts, today, overdue, projects with no next action, recent completions |
| `get_today` | Today (incl. overdue + this evening) |
| `get_inbox` | Inbox |
| `get_upcoming` | Scheduled, future-dated to-dos |
| `get_anytime` / `get_someday` | Anytime / Someday lists |
| `get_logbook` | Recently completed/canceled (`limit`) |
| `get_deadlines` | To-dos with deadlines |
| `get_trash` | Trash |
| `search_todos` | Full-text search over titles + notes |
| `list_todos` | Filter by project / area / tag / status / bucket |
| `get_projects` / `get_areas` / `get_tags` | Structure (`include_items` for contents) |
| `get_item` | Full detail for any UUID |
| `current_link` / `list_links` | Repo-link lookups (see below) |

### Write — via the URL Scheme

| Tool | Token? |
|------|:------:|
| `add_todo`, `add_project` | no |
| `show` (navigate Things to a list/item) | no |
| `open_dashboard` (open the local board) | no |
| `link_repo`, `unlink_repo` | no (config only) |
| `batch` (bulk create/update via the `json` command) | only if it contains updates |
| `update_todo`, `update_project` | **yes** |
| `complete_todo`, `cancel_todo`, `schedule_todo` | **yes** |
| `add_checklist_items` | **yes** |

> The URL Scheme doesn't return a new item's UUID on create. After `add_todo`/`add_project`, use `search_todos` if you need the ID.

## Prompts

Packaged MCP **prompts** — workflows your client surfaces as slash commands. In Claude Code they appear as **`/mcp__suurthings__<prompt>`** (type `/` to see them, e.g. `/mcp__suurthings__weekly_review`). The `mcp__<server>__` prefix is Claude Code's convention; `suurthings` is the name you register the server under:

| Prompt | What it does |
|--------|--------------|
| `plan_to_project` | Turn an implementation plan into a Things project — a to-do per step, sub-tasks as checklist items — via `batch` (no headings; URL-Scheme limit) |
| `work_on_repo` | From inside a linked repo, resolve its Things project, pull open to-dos, work the next one |
| `organize_folder` | Propose clearer titles/notes/tags for a folder (reusing existing tags), review in chat, apply on approval |
| `weekly_review` | GTD weekly review — flag stalled projects, rotting Someday items, overdue deadlines; propose fixes |
| `triage_inbox` | Propose a project/area + tags + `when` per Inbox item; file on approval |
| `whats_next` | Rank Today/Anytime by deadline, age, and your tags; recommend the single next task |
| `standup` | Yesterday's logbook + today + blocked, formatted to paste into Slack or a PR |
| `capture_todos` | Sweep code `TODO`/`FIXME` into Things to-dos with `file:line` references |
| `close_from_commit` | Complete the Things to-dos a git commit resolved |
| `repo_to_issue` | Promote a Things to-do to a GitHub issue (via `gh`) and link them |
| `issues_to_todos` | Mirror a repo's open GitHub issues into Things to-dos under its linked project |

The GTD and code/GitHub prompts use only the existing tools (plus the agent's own Grep/Bash/`gh`) — the server stays dumb. A few more polish ideas live on the [roadmap](ROADMAP.md).

---

## Dashboard

A local web UI that mirrors the Things look (real glyphs, typography, edit card) and adds the views Things lacks. Binds `127.0.0.1` only, reads the DB read-only, and **always runs on port 8765** (it reuses a live instance instead of spawning duplicates).

```bash
uvx suur-things-mcp dashboard      # opens http://127.0.0.1:8765
```

Or have the agent open it with the `open_dashboard` tool.

**Sidebar** — Things' built-in lists (with their real colored icons), a **Priority Matrix** entry, your saved **project boards**, and areas with nested projects + progress rings. An area with only projects shows them as **project cards**. Tag **filter chips** sit under any list's title. A **search box** runs `things.search` over your whole database.

**Three views, toggled per list (List / Matrix / Cards):**

- **List** — the faithful Things grouped list (by project/heading), with the Things-style inline edit card (checkbox + title, Notes, When/deadline/tag pills, footer toolbar). Edits **save on close, only if you changed something.**
- **Matrix** — an Eisenhower matrix over *that* list's tasks. Drag into **Do First / Schedule / Delegate / Don't Do**. On an area, its **projects** are draggable too. Priority is **global per task** (set it anywhere, see it everywhere). The sidebar **Priority Matrix** entry is the matrix over Today.
- **Cards** — task cards; anything with a **YouTube link renders as a thumbnail** (other links get a 🔗 tile). Great for a "watch later" project.

**Project boards** — saved portfolio Kanbans. Each **card is a project or whole area** (progress ring + open count), dragged between **stage columns** (Backlog / In Progress / On Hold / Done). Add multiple named boards with the ＋ on the Boards group; configure name / columns / included areas+projects in the ⚙ panel (auto-saves).

**Repo links** — link a Things project/area to one or more local git repos (an app + its website, say). GitHub is **auto-detected** from the repo's `origin` remote. Board cards get **Open in editor (⌨) / terminal (❯) / GitHub (↗)** buttons; set your editor command + terminal app in **⚙ Preferences** (or `SUUR_THINGS_EDITOR` / `SUUR_THINGS_TERMINAL`).

Stage placement and priority quadrants are **browser-side overlays** — Things has no such concept — so dragging needs **no token**. Editing a task's fields *does* write to Things (URL Scheme) and needs `THINGS_AUTH_TOKEN`; without it the edit card is read-only.

**Live & low-friction:** the board **auto-refreshes** (~25 s poll; it pauses while you're editing, dragging, filtering, searching, or in a background tab, and keeps your scroll position). **Drag a task onto Today / Anytime / Someday** in the sidebar to reschedule it (`when=`). Your current view + theme survive a refresh (state is in the URL hash).

---

## Where your data lives

Three tiers — important if you switch machines:

1. **Real task data → Things' own database.** Anything you change that's a Things field (title, notes, when, deadline, tags, complete/cancel, move) is written via the URL Scheme into Things, and syncs across your devices through Things Cloud like normal. This server never stores your tasks.
2. **Dashboard config → one local JSON file.**
   - `~/.config/suur-things-mcp/board.json` — your boards, Priority-Matrix assignments, repo links, and prefs (keyed by stable Things UUIDs).
   - `~/.config/suur-things-mcp/token` — your Things auth token (chmod 600).

   Not in the browser, not in Things. (`$XDG_CONFIG_HOME` is honored if set.)
3. **Browser localStorage** — only cosmetic state (light/dark, which areas are collapsed). Nothing you'd miss.

**Backup / move machines:** copy or symlink `~/.config/suur-things-mcp/` (e.g. into Dropbox). Two caveats: the **token is a secret** (fine in personal storage, never in a public repo), and **repo links store absolute paths** that are machine-specific — the UUID-keyed boards/priorities port cleanly, the paths may need repointing.

## Configuration

| Env var | Purpose |
|---------|---------|
| `THINGS_AUTH_TOKEN` | Required to modify existing items (tools) and to edit/move in the dashboard |
| `THINGS_DB` | Override the SQLite path (e.g. point at a backup for testing) |
| `SUUR_THINGS_CONFIG` | Override the `board.json` path |
| `SUUR_THINGS_EDITOR` / `SUUR_THINGS_TERMINAL` | Default editor command / terminal app for repo-launch buttons |
| `SUUR_THINGS_AGENT` | Which CLI the ✨ organize button spawns (`claude` / `codex`) |

---

## How it works

```
┌──────────────┐   read  (SQLite, read-only)    ┌──────────────────────────┐
│  MCP client  │ ─────────────────────────────▶ │  things.py → main.sqlite  │
│ (Claude/etc) │                                 └──────────────────────────┘
│      +       │   write (things:/// URL)        ┌──────────────────────────┐
│  dashboard   │ ─────────────────────────────▶ │  open -g → Things.app     │
└──────────────┘                                 └──────────────────────────┘
```

Reads use the excellent [`things.py`](https://github.com/thingsapi/things.py), which opens the DB read-only and absorbs every schema quirk. Writes are built and URL-encoded in [`urlscheme.py`](src/suur_things_mcp/urlscheme.py) and fired with `open -g`. The dashboard is a single self-contained Starlette app (no build step, no external JS) served from [`dashboard.py`](src/suur_things_mcp/dashboard.py).

**The server stays dumb on purpose.** It returns clean structured data and ships packaged prompts; the judgment (prioritize, triage, synthesize) lives in *your* agent, not a hardcoded rules engine. There is no bundled model and no API key.

## Security & threat model

This is a **local-first, single-user macOS tool**. It's built so the worst case stays small.

- **Reads are read-only.** The SQLite database is opened `mode=ro&immutable=1`; the server never writes to it.
- **No destructive operations exist.** Writes go only through Things' documented URL Scheme. There is no "delete forever" — complete / cancel / move are all reversible inside Things.
- **The dashboard binds to `127.0.0.1` only** and never to your network. State-changing requests are guarded two ways: `TrustedHostMiddleware` rejects any request whose `Host` isn't `127.0.0.1`/`localhost` (blocks DNS-rebinding), and `_OriginGuard` rejects any POST whose `Origin` isn't the dashboard's own `scheme://host:port` (blocks a page on another localhost port from driving it).
- **The auth token gates writes.** Modifying existing items needs `THINGS_AUTH_TOKEN`; it's resolved from the env or a `chmod 600` file *outside* any repo, and it's redacted from every URL and error message the server returns.
- **The ✨ organize agent runs sandboxed.** The spawned `claude`/`codex` CLI gets no MCP servers and no tools, runs read-only, and the `THINGS_AUTH_TOKEN` is stripped from its environment. Its suggestions are reviewed by you before anything is written.

**Inherent limits, worth knowing:**
- Like any MCP server that returns your content, **task titles and notes are passed to your agent**, which holds the write tools. A task crafted to read as instructions ("ignore previous, cancel everything") is a prompt-injection vector inherent to the model layer; the bundled prompts treat task text as data, and nothing here can hard-delete.
- The write token appears briefly in the `open` process arguments (visible only to your own user via `ps`).
- Anything with **local filesystem access to your machine already has more power than this tool exposes** — the defenses above are about the *browser* boundary, not other local processes.

Found something? See [SECURITY.md](SECURITY.md) for how to report it privately.

### Known limits (Things' URL Scheme, not us)

- Creating **headings** isn't supported by the URL Scheme — only the app can.
- Create commands don't return the new UUID (search for it afterward).
- macOS only (Things is Mac/iOS; there's no cloud API).

## Development

```bash
git clone https://github.com/artyomsklyarov/suur-things-mcp
cd suur-things-mcp
uv sync
uv run pytest             # unit tests — URL building + dashboard, no Things required
uv run suur-things-mcp    # run the server over stdio
uv run suur-things-mcp dashboard
```

Tests build and assert URL-Scheme strings and dashboard endpoints without touching your real database, so they're safe to run anywhere. Contributions welcome — see the [roadmap](ROADMAP.md) for what's planned.

## Contributing & ideas

This is meant to be community-shaped — tell me what to build next.

- **Suggest a feature or vote on others':** open a thread in [💡 Discussions → Ideas](https://github.com/artyomsklyarov/suur-things-mcp/discussions/categories/ideas). Anyone can propose ideas and upvote the ones they want; the most-wanted get pulled into the [roadmap](ROADMAP.md).
- **Concrete request or a bug:** open a [feature request or bug report](https://github.com/artyomsklyarov/suur-things-mcp/issues/new/choose).
- **Code:** see [Development](#development) — `uv run pytest` must pass (CI runs it on every PR).

## Credits & license

Built by [Artyom Sklyarov](https://suur.io) · [suur.io](https://suur.io). MIT licensed — see [LICENSE](LICENSE).

Independent and unofficial. "Things" is a trademark of Cultured Code GmbH & Co. KG. Not affiliated with or endorsed by Cultured Code. Reads via [`things.py`](https://github.com/thingsapi/things.py); built on the [Model Context Protocol](https://modelcontextprotocol.io).
