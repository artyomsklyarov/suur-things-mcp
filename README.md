# SUUR Things MCP

An [MCP](https://modelcontextprotocol.io) server for [**Things 3**](https://culturedcode.com/things/) (Cultured Code) on macOS. Let Claude Code, Claude Desktop, Codex, or any MCP-capable agent read and manage your tasks, projects, and areas.

- **Reads** come straight from the local Things SQLite database — instant and complete (Today, Upcoming, Inbox, Logbook, search, projects, areas, tags, full item detail).
- **Writes** go *only* through the official [Things URL Scheme](https://culturedcode.com/things/support/articles/2803573/) — add to-dos and projects, update, complete, cancel, reschedule, and append checklist items.

## Why this design is safe

Cultured Code's own [AI-integration guidance](https://culturedcode.com/things/support/articles/5510170/) is explicit: **writing directly to the Things database is unsafe and can corrupt it**, and they endorse the URL Scheme, Apple Shortcuts, and AppleScript as the safe automation paths.

This server follows that guidance exactly — it **reads** the database (read-only) and **never writes** to it. Every mutation is sent through the URL Scheme, the same mechanism Things itself documents for automation.

> **Privacy note:** an AI agent connected to this server can read the contents of your to-dos and notes. That content is sent to whatever model/agent you connect. Review your agent's privacy policy before connecting.

## Requirements

- macOS with [Things 3](https://culturedcode.com/things/) installed
- [`uv`](https://docs.astral.sh/uv/) (recommended) — or any Python ≥ 3.10 environment

## Install

The easiest path is `uvx`, which runs the server without a manual install:

```bash
uvx suur-things-mcp
```

### Claude Code

```bash
claude mcp add things -- uvx suur-things-mcp
```

To enable the write tools that modify existing items (update/complete/cancel/schedule), pass your auth token (see below):

```bash
claude mcp add things --env THINGS_AUTH_TOKEN=your-token-here -- uvx suur-things-mcp
```

### Claude Desktop / Codex / other clients

Add this to your client's MCP config (e.g. `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "things": {
      "command": "uvx",
      "args": ["suur-things-mcp"],
      "env": {
        "THINGS_AUTH_TOKEN": "your-token-here"
      }
    }
  }
}
```

`THINGS_AUTH_TOKEN` is **optional**. Without it you can still read everything and *create* new to-dos/projects. It's only required to **modify existing items**.

## Getting your Things auth token

1. Open **Things → Settings → General**
2. Enable **"Enable Things URLs"**
3. Click **Manage** and copy your token

Keep it secret — it grants write access to your database via the URL Scheme.

## Tools

### Read (no token required)

| Tool | What it returns |
|------|-----------------|
| `overview` | One-call system digest: counts, today, overdue, projects with no next action, recent completions |
| `get_today` | Today list (incl. overdue + evening) |
| `get_inbox` | Inbox |
| `get_upcoming` | Scheduled, future-dated to-dos |
| `get_anytime` | Anytime list |
| `get_someday` | Someday list |
| `get_logbook` | Recently completed/canceled (`limit`) |
| `get_deadlines` | To-dos with deadlines |
| `get_trash` | Trash |
| `search_todos` | Full-text search over titles + notes |
| `list_todos` | Filter by project / area / tag / status / bucket |
| `get_projects` | All projects (`include_items`) |
| `get_areas` | All areas (`include_items`) |
| `get_tags` | All tags (`include_items`) |
| `get_item` | Full detail for any UUID |

### Write via URL Scheme

| Tool | Token? |
|------|:------:|
| `add_todo` | no |
| `add_project` | no |
| `show` (navigate Things to a list/item) | no |
| `open_dashboard` (open the local Kanban board) | no |
| `batch` (bulk create/update via the `json` command) | only if it contains updates |
| `update_todo` | **yes** |
| `update_project` | **yes** |
| `complete_todo` | **yes** |
| `cancel_todo` | **yes** |
| `schedule_todo` | **yes** |
| `add_checklist_items` | **yes** |

> The URL Scheme does not return the new item's UUID on create. After `add_todo`/`add_project`, use `search_todos` if you need the ID to operate on it.

## Prompts

The server ships MCP **prompts** — packaged workflows your client surfaces as slash
commands (exact name/prefix is client-controlled):

| Prompt | What it does |
|--------|--------------|
| `plan_to_project` | Hand it an implementation plan; the agent uses `batch` to materialize a Things project (headings per phase, to-dos per step, checklist items per sub-task) |
| `work_on_repo` | From inside a linked repo, the agent resolves which Things project/area it maps to, pulls that project's open to-dos, and works the next one |

### Repo links

Link a Things project or area to one or more local git repos (an app + its website,
say) with `link_repo` / `unlink_repo` / `list_links`, or the 🔗 button on a board card.
The link lives in `board.json` (never written to Things). Then `current_link` lets an
agent sitting in a repo discover its project's tasks (it resolves your working dir via
`CLAUDE_PROJECT_DIR` or an explicit `cwd`), and board cards get Open-in-editor /
Open-on-GitHub buttons. The Phase-2 GitHub issue bridge is on the [roadmap](ROADMAP.md).

More GTD prompts (`weekly-review`, `triage-inbox`, `whats-next`, `standup`) are on the [roadmap](ROADMAP.md).

## Dashboard

A local web dashboard with two views and a light/dark toggle:

```bash
# standalone (opens your browser)
uvx suur-things-mcp dashboard
```

Or have the agent open it via the `open_dashboard` tool. The server binds
`127.0.0.1` only and reads the database read-only.

One two-pane layout. The **sidebar** holds Things' built-in lists, a **Priority Square**,
your saved **project boards** (compact group, right after Today), and your areas with
nested projects. Your current view is kept on refresh (it's in the URL hash).

**Project boards** — a portfolio Kanban that operates *on top of* Things. Each **card is
a project or an entire area** (a high-level overview: progress ring + open-task count),
not a task. Drag a card between **stage columns** (Backlog / In Progress / On Hold / Done)
to track where each project stands; click a card to open that project/area. Configure via
the ⚙ panel (Notion-style):

- **Name** — boards are saved; add as many as you like (e.g. "My Projects", "Client
  Projects") with the ＋ on the Boards group.
- **Columns** — your project stages; rename/add/remove freely.
- **Include** — check a **whole area** (great for meta-project areas) or **specific
  projects**. Inclusion is area/project level, never single tasks.
- Changes in the ⚙ panel **save automatically**; **Delete board** lives there too.
  Project cards show the project's description; areas collapse in the sidebar; your
  current view and theme survive a refresh, and the browser Back button works.

**Priority Square** — an Eisenhower matrix over your Today list. Drag tasks into **Do
First / Schedule / Delegate / Don't Do** to plan your day.

Project-stage placement and priority quadrants are **browser-side overlays** (stored in
`board.json`, never written to Things — Things has no such concept), so dragging needs
**no auth token**.

**Editing** — click any task (list or Priority Square) to open an edit dialog (title,
notes, when, deadline, tags, complete/cancel). This *does* write to Things via the URL
Scheme and needs `THINGS_AUTH_TOKEN`; without it the edit dialog is read-only.

Config is stored at `$XDG_CONFIG_HOME/suur-things-mcp/board.json` (`~/.config/...` by default).

## Configuration

| Env var | Purpose |
|---------|---------|
| `THINGS_AUTH_TOKEN` | Required to modify existing items (tools) and to edit/move cards in the dashboard |
| `THINGS_DB` | Override the SQLite path (e.g. point at a backup for testing) |
| `SUUR_THINGS_CONFIG` | Override the dashboard board-config path |

## Development

```bash
git clone https://github.com/artyomsklyarov/suur-things-mcp
cd suur-things-mcp
uv sync
uv run pytest          # unit tests (URL building — no Things required)
uv run suur-things-mcp # run the server over stdio
```

## How it works

```
┌──────────────┐   read (SQLite, read-only)    ┌─────────────────────────┐
│  MCP client  │ ───────────────────────────▶  │  things.py → main.sqlite │
│ (Claude/etc) │                                └─────────────────────────┘
│              │   write (things:/// URL)       ┌─────────────────────────┐
│              │ ───────────────────────────▶  │  open → Things.app       │
└──────────────┘                                └─────────────────────────┘
```

Reads use the excellent [`things.py`](https://github.com/thingsapi/things.py) library, which opens the database read-only and handles every schema quirk. Writes are built and URL-encoded in [`urlscheme.py`](src/suur_things_mcp/urlscheme.py) and executed with `open -g`.

## Credits & license

Built by [Artyom Sklyarov](https://suur.io) — [suur.io](https://suur.io).

MIT licensed. See [LICENSE](LICENSE).

This is an independent, unofficial project. "Things" is a trademark of Cultured Code GmbH & Co. KG. Not affiliated with or endorsed by Cultured Code.
