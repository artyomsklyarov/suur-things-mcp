# SUUR Things MCP — technical specification

Updated: 2026-10-10. Scope: 0.10.0 source and its release preparation. Product behavior is in [CONTEXT.MD](CONTEXT.MD); evidence/publication state is in [STATUS.MD](STATUS.MD). Source is authoritative when a historical README/roadmap disagrees with current behavior.

## Package, platform and stack

| Component | Specification |
|---|---|
| Package / command | `suur-things-mcp` / `suur-things-mcp` |
| Runtime | Python >=3.10, macOS with Things 3 for live functionality |
| License / maturity | MIT; package classifier Beta |
| Dependency manager | `uv`, committed `uv.lock` |
| Build | Hatchling, source distribution and wheel |
| Version authority | `src/suur_things_mcp/__init__.py::__version__`; Hatch reads it through `[tool.hatch.version]`; `pyproject.toml` uses dynamic version |
| MCP | `mcp>=1.2.0`, FastMCP, default stdio transport |
| Things reader | `things.py>=1.0`; the 0.10.0 floor documents reliance on created/modified fields |
| HTTP | `starlette>=0.37`, `uvicorn>=0.30`; synchronous I/O moved to thread pool where appropriate |
| Frontend | Packaged `static/index.html`, vanilla HTML/CSS/JavaScript, no frontend bundler/framework |
| Storage | Things SQLite read-only; local JSON overlay and attachment files |
| Tests | pytest >=8, httpx >=0.28.1, pytest-playwright >=0.5, Chromium |
| Lint | Ruff >=0.8, target `py310`, 120-character configured line length; E4/E7/E9/F/I/B/UP selected |

Minimum requirements are distinct from installed versions. The latest verified local toolchain uses Python 3.14.2, mcp 1.28.0, things.py 1.0.1, Starlette 1.3.1, uvicorn 0.49.0, pytest 9.1.1, Ruff 0.15.21 and Playwright 1.60.0. This is not a certification of every supported Python/macOS/Things combination. The Python/platform floor was not raised by the autoloop.

## Module boundaries

| File | Responsibility |
|---|---|
| `server.py` | FastMCP tools/prompts, compact projections, parameter validation, URL dispatch/write observation, CLI dispatch |
| `reads.py` | `things.py` queries plus read-only SQL aggregates; sidebar/list/card/detail/overview/staleness shapes |
| `urlscheme.py` | URL encoding, auth injection, `open -g` execution, token-redacted results/errors |
| `config.py` | Overlay normalization, recovery, locking, atomic writes, links, attachments and token lookup |
| `dashboard.py` | Starlette routes, host/origin/CSP policies, lifecycle, loopback service and agent jobs |
| `organize.py` | Agent selection/command, proposal prompt, environment filtering, process execution, parsing and submitted-ID boundaries |
| `static/index.html` | The complete frontend: theme/layout, routes, views, forms, focus lifecycle, API calls and refresh |
| `tests/` | Synthetic database, URL/mutation mocks, API/config failures/concurrency and real-browser tests |
| `.autoloop/` | Historical improvement state, evidence, strict fixture harness and safe capture tooling |

The module invariants are read-only task storage, official URL Scheme task writes, and separate local planning metadata. No ORM migration or application-owned canonical task database exists.

## Read path and data shapes

`reads._DB` captures the optional `THINGS_DB` override; normal discovery is delegated to things.py. SQL uses SQLite URI read-only mode. Some aggregation snapshots use `immutable=1`; they must not be treated as writable connections. Queries are constrained to the relevant item kinds, state and trash flags.

Compact cards are derived from full things.py items. Typical keys include `uuid`, `title`, `status`, `type`, `start`, `start_date`, `deadline`, `tags`, `project_title`, `heading_title`, `area_title`, `has_notes`, `link`, `age_days` and `idle_days` (actual null/presence follows the source projection). Full notes/checklists/timestamps remain in full-item reads. `compact=false` opts out of projection; list limits apply before projection. Zero/negative generic limits yield an empty slice, while annotated tool parameters have explicit bounds.

Area roll-up combines loose tasks with project tasks when enabled. Project progress and board counts come from source records. The sidebar returns built-ins, areas with projects, arealess projects and tags. Dashboard detail combines canonical item data with relevant local repositories/attachments; it does not persist a copy of the whole task record.

### Staleness query contract

`stale_review(never_touched_days=365, idle_days=180, inbox_idle_days=90, limit=40)` delegates to `stale_cohorts`. MCP validates thresholds 1–3650 and limit 1–200. The SQL selects open, untrashed to-dos, joining project titles; no write is dispatched.

- Inbox criterion: `start == 0` and idle days strictly exceed the Inbox threshold.
- Never-touched criterion: age strictly exceeds the threshold and creation/modification stamps differ by <60 seconds.
- Deferred criterion: nonzero packed start date is before today's packed date.
- Loose criterion: parent project is null and idle days exceed the general threshold.
- Remaining idle records are summarized by project title; this is currently title-based, not UUID-based grouping.
- Each cohort returns `{total, items}`; `items` is sliced to `limit`, totals are not.
- Additional keys: `counts`, `age_histogram`, `thresholds`, `clusters`, `dead_projects`.
- Packed scheduling date uses `(year << 16) | (month << 12) | (day << 7)`; unpacking extracts those fields.

Known hardening targets: absent/future timestamps, exact histogram boundaries, duplicate project titles, heading-only project emptiness and live snapshot/WAL behavior. Current tests establish fixture cohorts/disjointness/limits/read-only behavior, not every schema/edge case. Age is a factual signal; motivation/value is not a field this query can infer.

## MCP inventory

### Read tools (16)

`get_today`, `get_inbox`, `get_upcoming`, `get_anytime`, `get_someday`, `get_logbook`, `get_deadlines`, `get_trash`, `search_todos`, `list_todos`, `get_projects`, `get_areas`, `get_tags`, `get_item`, `overview`, `stale_review`.

The five ordinary list tools accept compact/limit controls; Logbook defaults to 50 and validates up to 500. Search defaults to 50 and validates 1–500. Structure tools can include contents. `get_item` retrieves one UUID. `overview` composes a digest; `stale_review` has its own shape and bounded cohorts.

### Canonical write/navigation tools (11)

`add_todo`, `add_project`, `update_todo`, `update_project`, `complete_todo`, `cancel_todo`, `schedule_todo`, `add_checklist_items`, `show`, `open_dashboard`, `batch`.

Task creation accepts title/notes/when/deadline/tags/checklist/destination and optional heading within an existing project. Project creation accepts area, dates/tags/notes and initial to-do titles. Update supports replacing or appending/prepending notes, tags, scheduling, destinations and checklists according to the official command's fields. Checklist parameter lists cap at 100. Empty deadline strings intentionally clear that field; omitted/None values do not clear it.

`show` and `open_dashboard` navigate/open local UI rather than mutate task fields. `batch` caps operation count at 250 and serialized JSON length at 100,000 characters (the source cap is a string length, not a strict UTF-8 byte limit). Pure-create batches need no token; any update operation requires one. Nested project creation is supported within the Things JSON format.

### Local integration tools (5)

`link_repo`, `unlink_repo`, `attach_image`, `list_links`, `current_link`. These operate on local overlay data. `attach_image` optionally appends a Things note reference if auth is available. Repo lookup uses explicit `cwd`, then client context (`CLAUDE_PROJECT_DIR`), then process cwd; longest contained path wins and missing repo paths are skipped.

### Prompts (13)

`plan_to_project`, `work_on_repo`, `organize_folder`, `weekly_review`, `triage_inbox`, `whats_next`, `standup`, `capture_todos`, `close_from_commit`, `repo_to_issue`, `issues_to_todos`, `calm_today`, `stale_sweep`. Their implementations return workflow text, not a tool-execution job. Client behavior and user approval still determine external actions.

## URL Scheme execution and acceptance

`build_url` percent-encodes parameter values, preserves explicit empty strings, drops None and serializes bools to `true`/`false`. `run_url` invokes `open -g` with a 10-second launch timeout. Updates/update-project require a token by default; JSON batches dynamically opt into auth. Returned URLs and errors redact both raw and encoded auth tokens.

MCP update helpers reject a UUID that can be confirmed absent. After dispatch they observe the item's `modified` stamp up to ten times at 0.2-second intervals. `applied=true` means a changed stamp was observed; `applied=false` means no change was observed within that window. Verification can be absent when the pre-write stamp is unreadable. Unknown requested tags produce a warning because Things can drop them.

This is not field-by-field verification, compare-and-swap or transactional acceptance. Batch returns dispatch/count information without individual outcome verification. Dashboard `/api/update` similarly returns dispatch success. `/api/add` can optionally resolve a created UUID for attachment workflows; that is a separate read/search step. Release documentation must preserve these distinctions.

## Overlay persistence

Default location: `$XDG_CONFIG_HOME/suur-things-mcp/board.json`, falling back to `~/.config/suur-things-mcp/board.json`; `SUUR_THINGS_CONFIG` selects another path. Defaults include a named Project Board and supported empty sections. Config has no formal schema-version migration framework yet; normalizers support existing/legacy link forms and sanitize supported sections.

| Section | Shape and ownership |
|---|---|
| `boards` | Array of board objects: stable ID/name, ordered columns, included areas/projects and UUID-to-stage placement |
| `priority` | UUID-to-quadrant map using `do`, `schedule`, `delegate`, `eliminate` |
| `priority_levels` | Four tag-mapping entries; ranking is computed from canonical Things tags |
| `timeblocks` | UUID → `{date, start, mins}` local block |
| `links` | Item UUID → `{kind, repos:[{repo, github, label}]}` |
| `prefs` | Editor/terminal and supported `claude`/`codex` agent/nonempty model choices |
| `area_prefs` | Per-area roll-up setting |
| `attachments` | Item UUID → metadata list with server ID, MIME, name, optional caption, added date |

Section merge replaces only explicitly supplied supported sections under a cross-process flock (`.board.lock`), reading current data first so unrelated sections survive. Atomic saves use an exclusive sibling temporary file and `os.replace`; error cleanup does not remove original user data.

Missing config returns defaults. Invalid JSON/UTF-8/non-object roots preserve original bytes and create an exclusive sibling `board.json.corrupt-<sha256>` recovery. Matching payloads reuse the matching backup; mismatched recovery contents fail. Other read errors propagate rather than returning defaults that could overwrite unread data. Recovery details are in [docs/DEVELOPMENT-VERIFICATION.md](docs/DEVELOPMENT-VERIFICATION.md).

### Attachments

Image MIME types: PNG/JPEG/GIF/WebP/HEIC/HEIF. Dashboard upload cap: 12 MiB decoded data per image; per-item cap: 24 images. IDs allow alphanumeric/underscore/hyphen only and require full matches. Stored filenames use generated IDs and a known MIME extension. Resolved file paths must stay under the attachment root using component containment, including symlink handling.

Bytes live at `<config-parent>/attachments/<item-uuid>/<attachment-id>.<ext>`. The cap check, file write and metadata save hold the same existing cross-process lock. `/api/attachment` reconstructs paths from stored records, not a supplied filesystem path. Failed unsafe detach preserves bytes/metadata. This is local file storage, not content upload to Things.

After successful storage, optional note-reference synchronization catches ordinary exceptions at its best-effort boundary and returns `note_updated=false`; it must not report an upload failure and encourage duplicate storage. Full attachment bytes/metadata remain the successful result. There is no promise of atomicity across Things and local storage.

## Local HTTP contract

Preferred port 8765; bind address 127.0.0.1. Existing live dashboards are reused; tests/captures use ephemeral ports. Reads generally use query strings; POST bodies are JSON object roots. Missing/invalid JSON roots and malformed section/list types return 400. Many existing domain/I/O failures use HTTP 200 with `ok=false`; clients must inspect that envelope rather than HTTP status alone.

| Route | Method | Purpose / key input |
|---|---|---|
| `/` | GET | Nonce-injected packaged page |
| `/api/version` | GET | Running package version |
| `/api/cursor` | GET | Cheap DB/WAL/config change cursor |
| `/api/sidebar` | GET | Sidebar plus auth availability |
| `/api/items` | GET | List ID, completed limit and area roll-up |
| `/api/item` | GET | Item detail by `id` |
| `/api/search` | GET | Search query |
| `/api/board` | GET | Configured board by ID, columns/cards |
| `/api/config` | GET / POST | Load overlay / merge owned sections |
| `/api/link` | POST | Item ID/kind and repository list |
| `/api/update` | POST | Existing item `id` and allowed field changes; token required |
| `/api/add` | POST | Task/project creation; optional ID resolution |
| `/api/rename` | POST | Canonical title update |
| `/api/pulse` | GET | Linked repo activity |
| `/api/open` | POST | Recorded item/repo index and editor/terminal/GitHub target |
| `/api/attach` | POST | UUID, base64/data-URL image, MIME/name/caption |
| `/api/attachment` | GET | Recorded item/attachment ID |
| `/api/detach` | POST | Explicit recorded attachment removal |
| `/api/organize` | POST / GET | Start folder workflow / poll job ID |

Config/item/board read errors retain structured fallback fields with `ok=false`. Wrong repository-list types do not silently clear links; an explicit valid empty list still clears by existing user intent. Non-string attachment MIME is rejected. Storage errors have an error envelope.

## Security and process boundaries

- TrustedHostMiddleware accepts allowed loopback hosts and blocks hostile Host headers/DNS rebinding.
- Origin guard compares full scheme/host/port on writes and rejects non-same-origin Fetch Metadata. Local non-browser requests without those headers are allowed, so this is not an authentication system for every local process.
- Each page response has a script nonce and CSP; no inline event attributes. Bind actions with JS listeners. `esc()` protects untrusted values rendered through HTML.
- Version injection replaces a quoted marker with JSON serialization.
- Repo-open actions resolve recorded paths, not arbitrary request commands/paths; GitHub/repo values are normalized.
- Credentials stay outside source. Model/provider authentication is the user's existing configuration.
- Local operation is not equivalent to no networking: optional model execution, GitHub reads, YouTube thumbnails and opened external links can use networks.

## Organizer jobs

User CLI choices are `claude` and `codex`. Claude is invoked in print/JSON mode with empty MCP config, strict MCP configuration and no allowed tools. Codex uses `exec --sandbox read-only`; this is best-effort and not identical to disabling all tools/MCP. Agent selection follows configuration/environment and installed command availability.

Each job runs in an empty temporary cwd. Environment filtering removes Things auth and unrelated token/secret/password/API-key-shaped variables, while `_KEEP_ENV` retains the selected providers' own authentication/base-URL variables. Do not claim that every secret-like variable is removed.

The organizer accepts at most 25 tasks and has a 180-second timeout. Dashboard caps active jobs at one and deduplicates the same folder/workflow. Output parsing tolerates supported JSON/fence shapes and normalizes tags. Suggestions are restricted to submitted UUIDs; first proposal per UUID wins. User field selection controls Apply; notes/tags use additive operations in that flow. No live organizer account/model invocation was part of the autonomous verification.

## Frontend state and accessibility

Hash destinations include `#l/<id>` with `/m`, `/p`, `/c`, `/t` view suffixes, `#p`, `#pl`, `#b/<board-id>`, `#about`. The monotonic `VIEW_REQUEST` generation guards asynchronous view reads and placement rerenders against stale navigation. `CONFIG_READY` blocks writes before settings load. Config saves update local state only after success.

Refresh checks the change cursor every five seconds when the tab/view is eligible. Editing overlays, drag, rename, selection, context menus, search/filter/About and hidden tabs prevent interruption. Unchanged cursors skip list/sidebar rereads. Silent refresh preserves scroll and suppresses entrance motion; version checks support reload after upgrade. This is polling, not WebSockets or a push server.

Compact mode defaults at <=800px; cards simplify further at small widths. `?compact=0` and `?placement=0` retain diagnostic fallbacks. Advanced placement uses native named selects; Levels retains auth and mapped-tag requirements. Timeline dialog uses explicit start/duration validation and preserves unrelated blocks. Shared modal stack handles focus/inertness/Escape/return. No new animations were added in compact/placement work; existing reduced-motion policy remains.

## Verification and release

```sh
uv sync --dev
uv run playwright install chromium
.venv/bin/python .autoloop/scripts/verify.py release-0.10.0
```

The strict gate runs Ruff, compilation, all pytest tests and `uv build --offline` against a temporary seeded Things DB/config/token path. Its pytest JUnit report must contain executed tests with zero skips/errors/failures; packaging stops on incomplete verification. Mutation and organizer subprocess calls are mocked. The ordinary `uv run pytest` can still skip environment-dependent tests; that command alone is not equivalent to this gate.

Current complete local baseline is 238 passing tests, no skips, one existing Starlette/TestClient/httpx deprecation. No standalone typechecker is configured. `ruff format --check src tests` is advisory because baseline compact-style files are intentionally not broadly reformatted. New tests/scripts follow Ruff formatting.

Safe captures use `.autoloop/scripts/capture.py <label> [project|advanced|placement|slots]`, disposable data and ephemeral loopback servers. Read every image before visual judgments. Existing evidence covers desktop/390px both themes; interaction geometry covers 320/390/768px and desktop restoration.

Main is protected by the `test` status check and up-to-date PR requirement. Existing CI syncs dev dependencies, installs Chromium, lints and runs pytest on Ubuntu. The stricter complete fixture gate is local; remote CI's ordinary test command can have environment skips. A published GitHub Release triggers the existing `release.yml`: build with uv, then PyPI Trusted Publishing/OIDC in the `pypi` environment. No API token is committed. Workflow configuration/permissions are not changed by this release.

Release order: validate version/lock/changelog and package assets, commit the full intended checkout, push branch, pass CI, merge normally, publish a tag/release at the checked commit, then verify the release job and fresh PyPI version/file hashes. A tag or GitHub Release alone is not proof of PyPI publication; record each state separately in STATUS.
