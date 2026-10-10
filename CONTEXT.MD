# SUUR Things MCP — product context

Updated: 2026-10-10. Product reference for the 0.10.0 release. Read [STATUS.MD](STATUS.MD) for what has actually been verified or published; this document describes functionality and intended behavior. [SPEC.MD](SPEC.MD) owns technical contracts, [TODO.MD](TODO.MD) user actions, and [PLAN.MD](PLAN.MD) unimplemented work.

## Product and purpose

SUUR Things MCP connects Things 3 on macOS to an MCP-capable agent and adds a local dashboard with planning views that Things does not provide. It is an MIT-licensed, public Python package named `suur-things-mcp`, distributed through PyPI and developed at [artyomsklyarov/suur-things-mcp](https://github.com/artyomsklyarov/suur-things-mcp). Its maturity is published beta, not a newly started prototype.

The core value moment is: connect an agent, ask what needs attention, receive a structured view of real tasks, and choose a specific next action. The dashboard gives the same task system a visual surface: familiar lists, project boards, priorities, cards and a daily timeline. Planning metadata stays separate from Things; genuine task changes use Things' official URL Scheme.

The project is a companion to Things, not a replacement task database. It does not run its own task-sync service, own users' task accounts, bundle a model, sell a model subscription, or operate a hosted dashboard. It provides structured data and workflows; judgment remains with the user and their agent.

## Who it is for

- Things users who want to inspect or maintain their tasks from Claude Code, Claude Desktop, Codex or another MCP client.
- Developers who connect project plans to local repositories and use those plans inside a coding session.
- People who want extra planning surfaces without copying all their tasks into a second product.
- Users who need keyboard access, readable light/dark views and usable windows alongside their editor.

An installed agent or browser is not evidence that its account is authenticated or a live integration has passed. Optional organizer workflows depend on the user's own CLI, account and model access. The package is free; a chosen model/provider can have its own costs and privacy terms.

## The three sources of state

| State | Authority | Product expectation |
|---|---|---|
| Task/project/area titles, notes, scheduling, tags and completion | Things 3 | Read from Things; modify only through its official URL Scheme |
| Board definitions/stages, Matrix assignments, time blocks, repository links, preferences and attachment records | Local JSON overlay | Persist independently, keyed by Things UUID; never manufacture corresponding Things fields |
| Theme and collapsed-area presentation | Browser localStorage | Cosmetic; blocked or damaged storage must not stop startup |

Priority Levels is deliberately different from the Matrix: its tag-to-level mapping is local, but moving an item between levels changes its real Things tags. Matrix quadrant assignments and board stages are local planning metadata. A timeline block is not a calendar event or an estimate inferred from a task's text.

## Agent-facing task access

### Reading the system

The server exposes 32 MCP tools and 13 packaged prompts in this release. Reads need no Things auth token. Built-in lists include Today, Inbox, Upcoming, Anytime, Someday, Logbook, deadlines and Trash. Search covers titles and notes. Filtered listing supports project, area, tag, status and bucket. Projects, areas and tags can include contents; item detail retrieves a complete record by UUID.

List tools normally return compact cards to keep agent context small. Cards include identity/title/status, relevant dates, tags, project context, whether notes exist, a useful link when available, and age/idle signals. An agent can request full items or retrieve one item's details when it needs notes/checklists. Limits constrain returned lists rather than pretending to summarize unseen content.

`overview` is a one-call digest: list counts, Today, overdue deadlines, recent completions and projects without an open next action. It is a composition of actual reads, not a generated prioritization score. No tool infers that an old task is unimportant or that a missed date proves avoidance.

### Writing and navigating

Create a to-do or project, optionally with scheduling, tags, notes, checklist items, destination or initial tasks. Creating new items and navigating Things do not require the modification token. Updating existing tasks/projects, completing, canceling, scheduling and appending checklist items require the token.

The `batch` tool carries a bounded set of create/update operations through the Things JSON URL command. Update-containing batches require auth. It is a dispatch mechanism, not a transactional migration or an undo system. An agent must identify the exact records and changes being approved; bulk decisions must not silently include items absent from a capped preview.

Create URLs do not return the new UUID. The MCP client must subsequently search/read the created item if it needs identity. Existing MCP update tools inspect whether an item exists and watch its modification stamp after dispatch. That observation is useful confirmation but does not prove every requested field changed. Dashboard update responses and batch dispatch have a different verification boundary, detailed in SPEC and STATUS.

### Packaged workflows

| Prompt | Intended outcome |
|---|---|
| `plan_to_project` | Convert an implementation plan into a project with tasks/checklists; use titles/notes for phases because URL Scheme heading creation is unsupported |
| `work_on_repo` | Resolve the current local repo to its linked Things project/area, inspect open work and select a next task |
| `organize_folder` | Propose clearer titles/notes/tags, review them, then apply selected changes |
| `weekly_review` | Inspect missing next actions, stale work and deadlines; propose changes for approval |
| `triage_inbox` | Propose a destination, tags and scheduling for Inbox items |
| `whats_next` | Recommend a next task using available dates, age and tags; keep recommendation distinct from mutation |
| `standup` | Produce a summary of recent work, Today and blockers; the prompt does not send a message |
| `capture_todos` | Let the coding agent inspect TODO/FIXME text and create tasks with source references |
| `close_from_commit` | Let the agent connect a commit to resolved tasks and propose completion |
| `repo_to_issue` / `issues_to_todos` | Agent-side GitHub/Things workflows using the client's existing `gh` capability; no bundled GitHub write service |
| `calm_today` | Propose a smaller visible workload and revised scheduling; user chooses what changes |
| `stale_sweep` | Review an old backlog by cohorts, approve exact item lists and verify changes rather than auto-canceling by age |

These prompts guide the connected agent; they are not independent schedulers or background product features. A client may expose them as slash commands. Actions involving GitHub or messages remain actions of that client, subject to its own authorization.

## Staleness review in 0.10.0

`stale_review` makes a large backlog reviewable in groups instead of returning one undifferentiated list. Defaults are 365 days for never-touched age, 180 idle days for general stale items, 90 idle days for Inbox and 40 displayed items per cohort. Thresholds are configurable within validated bounds.

Four item cohorts are disjoint because assignment uses a fixed first-match order:

1. `inbox_stale`: open Inbox items idle beyond the Inbox threshold.
2. `never_touched`: old items whose creation and modification stamps are effectively equal.
3. `deferred`: open items with a scheduled start date before today.
4. `loose_stale`: items without a parent project idle beyond the general threshold.

Remaining idle work is summarized by project in `clusters`. `dead_projects` reports open projects the query finds without open child records. Full totals are separate from capped item samples; an age histogram shows the backlog's distribution. These are review heuristics, not statements about motivation or project value. Edge cases such as missing timestamps, duplicate project names and heading-only projects are explicitly future hardening work in PLAN.

The intended review is optional and nonjudgmental: users can keep, clarify, move, reschedule, cancel, skip a queue or leave an item unchanged. Cancellation must be chosen and approved for the exact list. The application has no “cancel every old task” automation. Canceled records remain in Things' Logbook; there is no destructive delete tool in this workflow.

## Dashboard experience

### Startup and navigation

`suur-things-mcp dashboard` opens a loopback-only local browser UI. `--app` requests a frameless Chromium-style window with normal-browser fallback; `--no-open` serves quietly. Existing launchd install/uninstall commands support an always-on local service, but service installation is a separate user action.

The preferred address is `http://127.0.0.1:8765`. A compatible live instance is reused; if a foreign process owns the port, implementation can use another available port. The sidebar provides built-in lists, global Matrix/Levels destinations, saved boards, areas/projects, Logbook, Trash and About. URL hashes preserve navigation and browser Back/Forward behavior.

Startup must tolerate cosmetic-storage failure. If settings cannot be read, the UI offers retry and blocks overlay writes until a successful load rather than overwriting unknown settings with defaults. Sidebar failure stays within the sidebar and preserves navigation/footer structure. An arealess project remains navigable even when it contains no tasks.

### List view and editing

Lists group tasks by project and heading, with an overdue section in Today. Empty states explain that there is no work and offer an Add task action targeting the current list. Area views can roll up the tasks inside projects; a per-area toggle chooses roll-up versus loose items.

A task opens a Things-style edit card containing title, notes, When, deadline, tags and attachments. Existing edits save on close only when changed. New items are explicitly added; closing an unsubmitted new card discards its draft rather than creating a task. Completion, cancellation, rescheduling, moving and opening in Things are available through appropriate actions. Read-only mode must communicate the auth requirement.

Shift-selection exposes bounded batch actions. Context menus offer task actions. Tag chips filter the current list. The command palette provides navigation, search, creation, view changes and relevant task actions. It is intentionally immediate; routine keyboard navigation should not wait through entrance animation.

### Matrix

The Eisenhower Matrix shows Do First, Schedule, Delegate and Don't Do with an Unsorted pool. It is available over Today or a specific list/project/area. Areas can include their projects as planning cards. Assignments are global per Things UUID, so a task has the same quadrant across views.

Drag placement remains supported. A named native destination selector provides the same placement without dragging. Editing/opening/completion actions have keyboard routes. A failed placement save retains the previous value; successful saves preserve focus when the user has not moved elsewhere.

### Priority Levels

P1–P4 uses a local mapping to existing Things tags. The first matching mapped tag determines a task's level. Moving it replaces mapped priority tags while preserving unrelated tags. Native selectors supplement drag. Unmapped destinations and unauthenticated real-tag changes are unavailable. Mapping configuration and actual tag mutation are separate operations.

### Cards

Cards offer a visual task surface, including YouTube thumbnails for detected YouTube links and link tiles for other URLs. They remain task records, not duplicated media data. Thumbnail loading can involve external image hosts; it is distinct from telemetry or a bundled cloud backend.

### Project boards

Portfolio boards contain entire projects or areas, with progress/open counts and custom stage columns. Boards have names, scopes and column order. Stage assignment changes only the overlay. Native per-card selectors and keyboard navigation supplement drag. Narrow screens retain deliberate horizontal stage scrolling rather than hiding stages or deleting actions.

### Timeline

The daily view has a 06:00–23:00 grid, a current-time indicator, an unscheduled pool and scheduled-task controls. Drag uses existing 15/30/60-minute choices. The Schedule dialog exposes a named native time field and duration; users can save, change, unschedule or cancel. New dialog-created blocks must fit the displayed day. Form defaults are visible choices, not inferred duration estimates.

Time blocks persist locally as date/start/minutes keyed by task UUID. They do not reschedule Things' canonical task date or create calendar entries. Failed saves retain the dialog and previous config, unrelated blocks remain intact, and a pending response must not replace a view navigated to afterward.

### Repository links and pulse

A project/area can link to multiple local repositories, optionally labeled and associated with a GitHub repo. Buttons open the recorded repo in an editor, terminal or GitHub. Preferences choose editor command/terminal; existing agent/model preferences must survive these edits.

`current_link` resolves a supplied path to the longest matching linked repo. Repo pulse uses local `git` and optional `gh` reads for recent activity/PR counts. These integrations do not imply that the server implements issue synchronization, deploys code or contacts collaborators automatically.

### Attachments

Images are stored beside the local config, with metadata in the overlay. Supported image MIME types, size/count caps and contained paths are enforced. With a Things token, the server can append a local `file://` note reference; note synchronization is best-effort and reported separately from successful storage.

Attachments are not uploaded to Things Cloud. Moving the overlay to another machine does not make the original machine's file references portable. Removing an attachment is an explicit existing user feature; autonomous maintenance must not delete user files as “cleanup.”

## Visual and accessibility intent

Preserve the quiet Things-inspired typography, colors, sidebar structure, glyphs and progress indicators. Light/dark themes use shared tokens. Completion and direct manipulation get restrained feedback; background polling does not pulse the page. Reduced-motion preferences remove movement while preserving feedback.

At widths <=800px, content uses the full window and navigation opens from a menu. Matrix/Levels/Timeline stack appropriately; compact card layouts remain readable. Tests cover 320, 390 and 768px and restoration of desktop layout. `?compact=0` and `?placement=0` are diagnostic fallbacks, not flags users must enable to get the completed improvements.

Dialogs have names and labeled fields, move focus inside, contain keyboard focus, make background content inert, close the topmost dialog on Escape and return focus appropriately. Sidebar, filters, palette selection and task controls expose state. Completed/canceled tasks must not present an active completion action. Measured color samples support readability, but the project has not claimed exhaustive accessibility conformance.

## Trust, privacy and boundaries

The application never writes directly to Things SQLite. That prevents this integration's direct database writes; it does not make every task mutation harmless or reversible. Token redaction, loopback binding, host/origin protections, CSP, escaping and constrained subprocesses protect specific boundaries. They are not blanket security guarantees.

Agents can receive task titles/notes from the MCP client or organizer request and send them to the provider the user selected. Organizer processes retain the credentials needed by that provider; the application strips unrelated secret-shaped environment variables. Codex uses a best-effort read-only sandbox, not the same enforcement as Claude's no-tools/no-MCP flags. Documentation must not describe all agent execution as impossible to misuse.

## Intended future direction

The immediate future is stronger live acceptance, compatibility and review confidence, not a larger feature list. Audit history, compensating undo, local semantic search, personal-history indexing, energy/quarter planning, voice and private sync are optional concepts from the dream journal. They are not promised features or active epics. Each needs explicit product decisions and, where applicable, privacy/dependency/account or permission work. PLAN records prerequisites and acceptance criteria; TODO keeps the user's actual next actions separate.
