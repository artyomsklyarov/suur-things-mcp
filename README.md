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

More GTD prompts (`weekly-review`, `triage-inbox`, `whats-next`, `standup`) are on the [roadmap](ROADMAP.md).

## Dashboard

A local web dashboard with two views and a light/dark toggle:

```bash
# standalone (opens your browser)
uvx suur-things-mcp dashboard
```

Or have the agent open it via the `open_dashboard` tool. The server binds
`127.0.0.1` only and reads the database read-only.

**Classic** — a faithful Things two-pane replica: sidebar (Inbox, Today, Upcoming,
Anytime, Someday, Logbook, Trash, then your areas with nested projects and progress
rings) and a main panel showing the selected list grouped by project (or by heading
inside a project), with tag pills, deadlines, and notes indicators.

**Board** — a custom Kanban that operates *on top of* Things. Columns are Things
**tags** (so your board state syncs to iOS and shows up in Things itself). Configure it
from the in-browser ⚙ settings panel:

- **Columns** — name each column; each is a Things tag (e.g. `Backlog`, `In Progress`,
  `On Hold`, `Done`). Optionally create them as nested tags under a `Kanban` tag in Things.
- **Include on board** — check the areas/projects whose to-dos populate the board.
- A card sits in the column whose tag it carries; included cards with no column tag land
  in a leading **Unsorted** column.

**Editing** — click any task (either view) to open an edit dialog (title, notes, when,
deadline, tags, complete/cancel), or drag a card between columns. Both write through the
URL Scheme and require `THINGS_AUTH_TOKEN`; without it the dashboard is read-only.

Board config is stored at `$XDG_CONFIG_HOME/suur-things-mcp/board.json`
(`~/.config/...` by default).

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
