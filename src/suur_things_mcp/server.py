"""SUUR Things MCP — an MCP server for Things 3 (Cultured Code) on macOS.

Reads come from the local SQLite database (safe, fast, read-only).
Writes go exclusively through the official Things URL Scheme.

Run:  suur-things-mcp        (stdio transport)
Env:  THINGS_AUTH_TOKEN      required only for update/complete/cancel/schedule
      THINGS_DB              optional path override for the SQLite database
"""

from __future__ import annotations

import json
import os
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from . import config as boardcfg
from . import reads
from .urlscheme import ThingsURLError, execute

mcp = FastMCP(
    "suur-things",
    instructions=(
        "Read and write the Things 3 task manager on macOS. Reads (today, "
        "upcoming, inbox, search, projects, areas, tags, get_item) are instant "
        "and safe. Writes (add_todo, add_project, update_todo, complete_todo, "
        "cancel_todo, schedule_todo, add_checklist_items) go through the "
        "official Things URL Scheme. Modifying existing items requires "
        "THINGS_AUTH_TOKEN to be set; creating new items does not. Use UUIDs "
        "returned by read tools to target items in write tools."
    ),
)


def _auth() -> str | None:
    return boardcfg.auth_token()


# =========================================================================
# READ TOOLS
# =========================================================================

@mcp.tool()
def get_today() -> list[dict]:
    """To-dos in the Today list (including overdue and evening items)."""
    return reads.today()


@mcp.tool()
def get_inbox() -> list[dict]:
    """To-dos in the Inbox (unsorted, no project or area yet)."""
    return reads.inbox()


@mcp.tool()
def get_upcoming() -> list[dict]:
    """Scheduled to-dos with a future start date (the Upcoming list)."""
    return reads.upcoming()


@mcp.tool()
def get_anytime() -> list[dict]:
    """To-dos in the Anytime list (actionable but not scheduled)."""
    return reads.anytime()


@mcp.tool()
def get_someday() -> list[dict]:
    """To-dos in the Someday list (on hold for later)."""
    return reads.someday()


@mcp.tool()
def get_logbook(
    limit: Annotated[int, Field(ge=1, le=500)] = 50,
) -> list[dict]:
    """Recently completed and canceled to-dos, newest first."""
    return reads.logbook(limit=limit)


@mcp.tool()
def get_deadlines() -> list[dict]:
    """To-dos that have a deadline, ordered by due date."""
    return reads.deadlines()


@mcp.tool()
def get_trash() -> list[dict]:
    """To-dos currently in the Trash."""
    return reads.trash()


@mcp.tool()
def search_todos(
    query: Annotated[str, Field(description="Full-text search over titles and notes.")],
) -> list[dict]:
    """Search across all to-dos and projects by title and notes."""
    return reads.search(query)


@mcp.tool()
def list_todos(
    project_uuid: str | None = None,
    area_uuid: str | None = None,
    tag: str | None = None,
    status: Literal["incomplete", "completed", "canceled"] | None = None,
    start: Literal["Inbox", "Anytime", "Someday"] | None = None,
) -> list[dict]:
    """Query to-dos with optional filters (project, area, tag, status, bucket).

    Pass a project_uuid or area_uuid from get_projects / get_areas to scope to
    one container. `start` filters by the Inbox/Anytime/Someday bucket.
    """
    return reads.todos(
        project_uuid=project_uuid,
        area_uuid=area_uuid,
        tag=tag,
        status=status,
        start=start,
    )


@mcp.tool()
def get_projects(include_items: bool = False) -> list[dict]:
    """All projects. Set include_items=true to embed each project's to-dos."""
    return reads.projects(include_items=include_items)


@mcp.tool()
def get_areas(include_items: bool = False) -> list[dict]:
    """All areas. Set include_items=true to embed each area's projects/to-dos."""
    return reads.areas(include_items=include_items)


@mcp.tool()
def get_tags(include_items: bool = False) -> list[dict]:
    """All tags. Set include_items=true to embed the items carrying each tag."""
    return reads.tags(include_items=include_items)


@mcp.tool()
def get_item(uuid: str) -> dict | None:
    """Full detail for any item by UUID — notes, checklist items, dates, tags."""
    item = reads.get(uuid)
    if item is None:
        return None
    return item


@mcp.tool()
def overview(
    recent_completed: Annotated[int, Field(ge=0, le=100)] = 10,
) -> dict:
    """One-call situational digest of the whole Things system.

    Use this FIRST to understand state cheaply instead of calling many read
    tools. Returns counts per list, today's items, overdue items, projects with
    no open next action, and recent completions.
    """
    return reads.overview(recent_completed=recent_completed)


# =========================================================================
# WRITE TOOLS — via the Things URL Scheme
# =========================================================================

def _tags(tags: list[str] | None) -> str | None:
    return ",".join(tags) if tags else None


def _lines(items: list[str] | None) -> str | None:
    return "\n".join(items) if items else None


@mcp.tool()
def add_todo(
    title: str,
    notes: str | None = None,
    when: Annotated[
        str | None,
        Field(description="today | tomorrow | evening | anytime | someday | yyyy-mm-dd | yyyy-mm-dd@HH:MM"),
    ] = None,
    deadline: Annotated[str | None, Field(description="yyyy-mm-dd")] = None,
    tags: list[str] | None = None,
    checklist_items: Annotated[list[str] | None, Field(description="Up to 100 items.")] = None,
    list_title: Annotated[str | None, Field(description="Destination project/area by title.")] = None,
    list_id: Annotated[str | None, Field(description="Destination project/area by UUID (wins over list_title).")] = None,
    heading: Annotated[str | None, Field(description="Heading within the destination project.")] = None,
    completed: bool = False,
    reveal: Annotated[bool, Field(description="Navigate Things to the new to-do.")] = False,
) -> dict[str, Any]:
    """Create a new to-do. No auth token required.

    Returns the executed URL. Note: the URL Scheme does not return the new
    item's UUID; use search_todos afterward if you need it.
    """
    params = {
        "title": title,
        "notes": notes,
        "when": when,
        "deadline": deadline,
        "tags": _tags(tags),
        "checklist-items": _lines(checklist_items),
        "list": list_title,
        "list-id": list_id,
        "heading": heading,
        "completed": completed or None,
        "reveal": reveal or None,
    }
    return _do("add", params)


@mcp.tool()
def add_project(
    title: str,
    notes: str | None = None,
    area: Annotated[str | None, Field(description="Destination area by title.")] = None,
    area_id: Annotated[str | None, Field(description="Destination area by UUID (wins over area).")] = None,
    when: str | None = None,
    deadline: str | None = None,
    tags: list[str] | None = None,
    todos: Annotated[list[str] | None, Field(description="Initial to-do titles to create inside the project.")] = None,
    reveal: bool = False,
) -> dict[str, Any]:
    """Create a new project, optionally pre-filled with to-dos. No auth token required."""
    params = {
        "title": title,
        "notes": notes,
        "area": area,
        "area-id": area_id,
        "when": when,
        "deadline": deadline,
        "tags": _tags(tags),
        "to-dos": _lines(todos),
        "reveal": reveal or None,
    }
    return _do("add-project", params)


@mcp.tool()
def update_todo(
    id: Annotated[str, Field(description="UUID of the to-do to modify.")],
    title: str | None = None,
    notes: Annotated[str | None, Field(description="Replaces existing notes.")] = None,
    prepend_notes: str | None = None,
    append_notes: str | None = None,
    when: str | None = None,
    deadline: Annotated[str | None, Field(description="yyyy-mm-dd, or empty string to clear.")] = None,
    tags: Annotated[list[str] | None, Field(description="Replaces all existing tags.")] = None,
    add_tags: Annotated[list[str] | None, Field(description="Adds to existing tags.")] = None,
    checklist_items: Annotated[list[str] | None, Field(description="Replaces all checklist items.")] = None,
    append_checklist_items: list[str] | None = None,
    list_title: str | None = None,
    list_id: str | None = None,
    heading: str | None = None,
    completed: bool | None = None,
    canceled: bool | None = None,
    reveal: bool = False,
) -> dict[str, Any]:
    """Modify an existing to-do. Requires THINGS_AUTH_TOKEN.

    Cannot modify repeating to-dos. `deadline=""` clears the deadline.
    """
    params = {
        "id": id,
        "title": title,
        "notes": notes,
        "prepend-notes": prepend_notes,
        "append-notes": append_notes,
        "when": when,
        "deadline": deadline,
        "tags": _tags(tags),
        "add-tags": _tags(add_tags),
        "checklist-items": _lines(checklist_items),
        "append-checklist-items": _lines(append_checklist_items),
        "list": list_title,
        "list-id": list_id,
        "heading": heading,
        "completed": completed,
        "canceled": canceled,
        "reveal": reveal or None,
    }
    return _do("update", params)


@mcp.tool()
def update_project(
    id: Annotated[str, Field(description="UUID of the project to modify.")],
    title: str | None = None,
    notes: Annotated[str | None, Field(description="Replaces existing notes.")] = None,
    prepend_notes: str | None = None,
    append_notes: str | None = None,
    when: str | None = None,
    deadline: Annotated[str | None, Field(description="yyyy-mm-dd, or empty string to clear.")] = None,
    tags: Annotated[list[str] | None, Field(description="Replaces all existing tags.")] = None,
    add_tags: Annotated[list[str] | None, Field(description="Adds to existing tags.")] = None,
    area: Annotated[str | None, Field(description="Move to area by title.")] = None,
    area_id: Annotated[str | None, Field(description="Move to area by UUID (wins over area).")] = None,
    completed: Annotated[bool | None, Field(description="Requires all child to-dos completed/canceled.")] = None,
    canceled: bool | None = None,
    reveal: bool = False,
) -> dict[str, Any]:
    """Modify an existing project. Requires THINGS_AUTH_TOKEN.

    Completing or canceling a project requires its child to-dos to already be
    completed/canceled. `deadline=""` clears the deadline.
    """
    params = {
        "id": id,
        "title": title,
        "notes": notes,
        "prepend-notes": prepend_notes,
        "append-notes": append_notes,
        "when": when,
        "deadline": deadline,
        "tags": _tags(tags),
        "add-tags": _tags(add_tags),
        "area": area,
        "area-id": area_id,
        "completed": completed,
        "canceled": canceled,
        "reveal": reveal or None,
    }
    return _do("update-project", params)


@mcp.tool()
def complete_todo(id: str) -> dict[str, Any]:
    """Mark a to-do as completed. Requires THINGS_AUTH_TOKEN."""
    return _do("update", {"id": id, "completed": True})


@mcp.tool()
def cancel_todo(id: str) -> dict[str, Any]:
    """Mark a to-do as canceled. Requires THINGS_AUTH_TOKEN."""
    return _do("update", {"id": id, "canceled": True})


@mcp.tool()
def schedule_todo(
    id: str,
    when: Annotated[str, Field(description="today | tomorrow | evening | anytime | someday | yyyy-mm-dd | yyyy-mm-dd@HH:MM")],
) -> dict[str, Any]:
    """Schedule (or reschedule) an existing to-do. Requires THINGS_AUTH_TOKEN."""
    return _do("update", {"id": id, "when": when})


@mcp.tool()
def add_checklist_items(
    id: str,
    items: Annotated[list[str], Field(description="Checklist item titles to append.")],
) -> dict[str, Any]:
    """Append checklist items to an existing to-do. Requires THINGS_AUTH_TOKEN."""
    return _do("update", {"id": id, "append-checklist-items": _lines(items)})


@mcp.tool()
def show(
    id: Annotated[
        str,
        Field(description="Item UUID, or a built-in list: inbox, today, anytime, upcoming, someday, logbook, tomorrow, deadlines."),
    ],
    filter_tags: Annotated[list[str] | None, Field(description="Tag titles to filter the shown list by.")] = None,
) -> dict[str, Any]:
    """Open Things and navigate to an item or built-in list. No auth token required."""
    return _do("show", {"id": id, "filter": _tags(filter_tags)})


@mcp.tool()
def open_dashboard() -> dict[str, Any]:
    """Open the local read-only Kanban board of your Things lists in the browser.

    Starts a tiny local web server (background, 127.0.0.1 only) and opens it.
    Idempotent: repeated calls return the same already-running URL. No data is
    written; cards deep-link back into Things.
    """
    from .dashboard import ensure_running

    try:
        url = ensure_running(open_browser=True)
        return {"ok": True, "url": url}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def batch(
    operations: Annotated[
        list[dict],
        Field(
            description=(
                "List of Things JSON operations. Each item is an object:\n"
                '  {"type": "to-do"|"project"|"heading"|"checklist-item",\n'
                '   "operation": "create"|"update",   # default "create"\n'
                '   "id": "<uuid>",                    # required when updating\n'
                '   "attributes": { ... }}             # title, notes, when, deadline,\n'
                "                                       # tags (array), checklist-items\n"
                "                                       # (array), list/list-id, area/area-id,\n"
                "                                       # heading, completed, canceled, and\n"
                "                                       # for projects: items (array). Update-only:\n"
                "                                       # prepend-notes, append-notes, add-tags,\n"
                "                                       # append-checklist-items."
            )
        ),
    ],
    reveal: Annotated[bool, Field(description="Navigate to the first created/updated item.")] = False,
) -> dict[str, Any]:
    """Create and/or update many items in one call via the Things `json` command.

    Fastest way to import a whole project with to-dos, or to change many items
    at once. An auth token is required ONLY if any operation is an "update";
    pure-create batches need no token.

    Example — a project with two to-dos:
        [{"type": "project", "attributes": {
            "title": "Launch", "area": "Work",
            "items": [
                {"type": "to-do", "attributes": {"title": "Draft post", "when": "today"}},
                {"type": "to-do", "attributes": {"title": "Publish", "when": "tomorrow"}}
            ]}}]
    """
    requires_auth = any(
        isinstance(op, dict) and op.get("operation") == "update" for op in operations
    )
    data = json.dumps(operations, ensure_ascii=False)
    try:
        execute(
            "json",
            {"data": data, "reveal": reveal or None},
            auth_token=_auth(),
            requires_auth=requires_auth,
        )
        return {
            "ok": True,
            "command": "json",
            "count": len(operations),
            "requires_auth": requires_auth,
        }
    except ThingsURLError as exc:
        return {"ok": False, "command": "json", "error": str(exc)}


# =========================================================================
# REPO LINKS — connect a project/area to one or more local git repos
# =========================================================================

@mcp.tool()
def link_repo(
    item_uuid: Annotated[str, Field(description="UUID of the Things project or area to link.")],
    repo_path: Annotated[str, Field(description="Absolute path to the local git repo.")],
    github: Annotated[str | None, Field(description="'owner/repo' or a github URL.")] = None,
    label: Annotated[str | None, Field(description="Optional label, e.g. 'iOS app' or 'Website'.")] = None,
) -> dict[str, Any]:
    """Link a local repo to a Things project/area. A project/area can have several.

    Stored in the browser-side config (never written to Things). Used by
    `current_link` (so an agent in that repo finds its tasks) and the dashboard.
    """
    detail = reads.get(item_uuid)
    if not detail:
        return {"ok": False, "error": "no project/area with that uuid"}
    kind = "area" if detail.get("type") == "area" else "project"
    boardcfg.set_link(item_uuid, kind, repo_path, github, label)
    return {"ok": True, "item_uuid": item_uuid, "kind": kind}


@mcp.tool()
def unlink_repo(
    item_uuid: str,
    repo_path: Annotated[str | None, Field(description="Remove just this repo; omit to remove all repos for the item.")] = None,
) -> dict[str, Any]:
    """Remove a repo link (or all of an item's repo links)."""
    boardcfg.remove_link(item_uuid, repo_path)
    return {"ok": True}


@mcp.tool()
def list_links() -> list[dict]:
    """All repo↔project/area links, with item titles resolved."""
    out = []
    for item_id, item in boardcfg.links().items():
        detail = reads.get(item_id)
        out.append({
            "item_uuid": item_id,
            "kind": item.get("kind"),
            "title": detail.get("title") if detail else None,
            "repos": item.get("repos", []),
        })
    return out


@mcp.tool()
def current_link(
    cwd: Annotated[
        str | None,
        Field(description="Absolute path of your current working directory. PASS THIS EXPLICITLY — the server's own cwd is unreliable under uvx."),
    ] = None,
) -> dict | None:
    """The Things project/area linked to your current repo, plus its open to-dos.

    Resolves the directory in order: `cwd` arg → CLAUDE_PROJECT_DIR env → the
    server's cwd. Returns null when the directory isn't under any linked repo.
    """
    path = cwd or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    link = boardcfg.link_for_path(path)
    if not link:
        return None
    item_id = link["item_id"]
    detail = reads.get(item_id)
    items = reads.list_items(item_id)
    return {
        "item_uuid": item_id,
        "kind": link["kind"],
        "title": detail.get("title") if detail else None,
        "resolved_path": path,
        "matched_repo": link["repo"],
        "repos": boardcfg.links().get(item_id, {}).get("repos", []),
        "open_tasks": items.get("items", []),
    }


# =========================================================================

def _do(command: str, params: dict) -> dict[str, Any]:
    """Execute a write command, returning a structured result the model can read."""
    try:
        url = execute(command, params, auth_token=_auth())
        return {"ok": True, "command": command, "url": url}
    except ThingsURLError as exc:
        return {"ok": False, "command": command, "error": str(exc)}


# =========================================================================
# PROMPTS — packaged workflows clients surface as slash commands
# =========================================================================

@mcp.prompt()
def plan_to_project(plan: str) -> str:
    """Turn an implementation plan into a tracked Things project."""
    return (
        "You are turning an implementation plan into a Things project using the "
        "`batch` tool (which calls the Things JSON command).\n\n"
        "Steps:\n"
        "1. Read the plan below. Infer a concise project title.\n"
        "2. Map the plan's phases/sections to project items: use `heading` items "
        "for phases and `to-do` items for concrete steps. Put sub-tasks of a step "
        "into that to-do's `checklist-items` (max 100).\n"
        "3. Call `batch` ONCE with a single project operation whose `attributes.items` "
        "array holds the headings and to-dos in order. Set a `when` of `anytime` "
        "unless the plan implies dates. Do not invent deadlines.\n"
        "4. This is a pure-create batch, so no auth token is needed. After it "
        "succeeds, tell the user the project title and how many to-dos were created. "
        "Use `search_todos` if you need the new project's id.\n\n"
        "Do not pad the project with steps that aren't in the plan. Keep titles "
        "short and action-first.\n\n"
        "--- PLAN ---\n"
        f"{plan}"
    )


@mcp.prompt()
def work_on_repo() -> str:
    """Find this repo's Things project and work its tasks."""
    return (
        "Help the user work on the Things project/area tracked in their current repo.\n\n"
        "1. Find your absolute working directory (e.g. `git rev-parse --show-toplevel`) "
        "and call `current_link` with cwd set to that path. PASS cwd EXPLICITLY — do not "
        "rely on the server's own cwd.\n"
        "2. If it returns null, there's no link yet. Detect the repo's remote "
        "(`git remote get-url origin`), find the matching Things project with "
        "`search_todos`/`get_projects`, and offer to `link_repo(item_uuid, repo_path, github)`. "
        "Note a project can have several repos (e.g. an app + its website) — link each.\n"
        "3. If linked, review `open_tasks`, pick the single highest-leverage next task, and "
        "propose it. When the work is done, close it with `complete_todo` (needs "
        "THINGS_AUTH_TOKEN).\n"
        "Stay scoped to this repo's project; don't pull in unrelated tasks."
    )


def main() -> None:
    import sys

    args = sys.argv[1:]
    if args and args[0] == "dashboard":
        from .dashboard import serve_foreground

        serve_foreground()
    else:
        mcp.run()


if __name__ == "__main__":
    main()
