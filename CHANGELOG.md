# Changelog

All notable changes to `suur-things-mcp` are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/); this project uses
[semantic versioning](https://semver.org/).

## [0.8.4] - 2026-06-22

### Fixed

- **The real fix for "Add looks dead" with an image.** v0.8.3 moved the slow page
  reads off the event loop, but the quick-add resolve poll still ran its
  `find_by_exact_title` lookups *through the same thread pool* — so if you tapped
  Add while the project's data was still loading (the repo pulse can hold threads
  on `git`/`gh` for seconds), those 3ms lookups **queued behind it** and the add
  stretched to ~5s. The resolve poll now runs its exact-match read **inline** (3ms
  on the loop, no thread-pool round-trip), so it can't be starved. Measured: the
  same "navigate to a project, immediately add with an image" dropped from ~5.3s to
  ~0.23s, even mid-load.

## [0.8.3] - 2026-06-22

### Fixed

- **Quick-add with an image no longer looks dead.** Adding a to-do with a staged
  image could take 5–8 seconds before the card closed (sometimes long enough that
  you gave up before the task was created). The read endpoints (`/api/state`,
  `/api/sidebar`, `/api/items`, `/api/item`, `/api/board`) still ran their SQLite
  reads **synchronously on the event loop** — so while the page loaded its data
  (the sidebar alone scans ~1.3k projects), the quick-add resolve poll's
  `asyncio.sleep` clock stretched from ~1.8s to many seconds. Those reads now run
  off the event loop (`run_in_threadpool`), bringing the same add from ~5.3s back
  to ~0.3s. (Completes the v0.8.0 blocking-handler fix, which only covered writes.)

## [0.8.2] - 2026-06-21

Quality pass: the deferred follow-ups from the v0.8.0 audit, dependency bumps,
and the project's first real JavaScript test coverage.

### Added

- **Headless-browser test harness** (pytest + Playwright). The dashboard ships its
  UI as embedded JS with no JS runner; `tests/test_dashboard_browser.py` now loads
  the real page in Chromium and asserts the client-side behaviours pure-Python
  tests can't reach — XSS escaping (`jsarg`), the quick-add re-entry guard + button
  feedback, and a clean (exception-free) boot. Tests skip when Chromium isn't
  installed, so plain `uv run pytest` still works; CI installs it and runs them.

### Changed

- **Quick-add UUID resolution is faster and more reliable.** Resolving a new item's
  UUID now uses an exact-title DB read (`find_by_exact_title`) instead of polling
  the `LIKE`-based search up to a dozen times — the old search could even miss the
  title entirely (its tokenization didn't always match), silently failing to link a
  staged image.
- **Centralized dashboard fetch error handling.** All ~29 frontend `fetch()` calls
  now go through `getJSON`/`postJSON` helpers that return `{ok:false, error}` on a
  network/parse failure instead of throwing silently — no more stale spinners when
  the server restarts.
- Dependency bumps: starlette 1.3.1, uvicorn 0.49, mcp 1.28, pytest 9.1.1;
  CI actions checkout v6 + setup-uv v8 (clears the pending Node-20 deprecation).

### Fixed (polish)

- Organize-job slot is now reserved under a lock, so two concurrent requests can't
  both pass the single-job cap.
- `ensure_running` waits for the server to accept connections before opening the
  browser (no more "connection refused" on a just-launched tab).
- SQLite read URIs are path-quoted (handles a DB path with spaces/`?`/`#`).
- `attach_image` checks file size before reading and uses a context-managed handle.
- Checklist inputs are capped at 100 items (`max_length`); attachments capped at 24
  per item so `board.json` can't grow unbounded.

## [0.8.0] - 2026-06-05

Security + robustness hardening pass, from a full-codebase review (eng review +
Codex audit). No behavior change for normal use.

### Security

- **Stored XSS in the dashboard fixed.** A project/area title was interpolated
  into an inline `onclick` JS string via `encodeURIComponent`, which doesn't
  escape `'` — a crafted title could execute script in the dashboard origin (which
  can drive same-origin APIs incl. opening local files/apps). Now escaped with a
  `jsarg()` helper that closes the `'` hole.
- **Path traversal on attachment upload fixed.** The `/api/attach` endpoint used
  the request's `uuid` directly as a directory name; a `../`-shaped value could
  write outside the attachments dir. `save_attachment` now validates the id and
  verifies the resolved path stays under the attachments dir.
- **Organizer agent hardened.** The spawned `claude`/`codex` CLI now runs in an
  empty temp directory with secret-shaped env vars stripped (tokens, API keys,
  cloud creds — the agent's own auth is preserved), so a prompt-injected task
  can't read+exfiltrate credentials. The docstring no longer overstates the Codex
  sandbox's guarantees.

### Fixed

- **Config can no longer be silently lost or corrupted.** `board.json` is now
  written atomically (temp file + `os.replace`), so an interrupted or concurrent
  write can't leave a truncated file. A genuinely corrupt config is backed up to
  `board.json.corrupt-<timestamp>` instead of being silently replaced with empty
  defaults (which the next save used to make permanent).
- **Dashboard no longer freezes during writes/pulse.** Blocking work — the Things
  URL-scheme `open`, `git`/`gh` subprocesses, and SQLite searches — now runs off
  the event loop (`run_in_threadpool`), so one slow request can't stall the whole
  dashboard.
- **POST endpoints validate input.** Malformed JSON or wrong-typed fields (e.g.
  `tags: "abc"`) return a structured 400/error instead of a 500.
- `batch` now caps operation count (250) and serialized size (~100KB) before
  building the URL, instead of risking an oversized `open` argv.
- Dashboard search routes through `reads.search`, so the `THINGS_DB` override is
  honored (and the query runs off the event loop).

## [0.7.3] - 2026-06-05

### Added

- **`dashboard --no-open`** — run the dashboard as a quiet background service:
  bind the port and serve, but never open a browser. Intended for a login agent
  (launchd/systemd) that keeps the dashboard alive across restarts without popping
  a tab every time. Without it, a `KeepAlive` agent that loses the port (e.g. a
  second instance grabbed it) relaunches in a loop, opening a browser on each
  restart.

## [0.7.2] - 2026-06-05

### Fixed

- **Add button could get stuck disabled forever.** The 0.7.1 fix disabled the
  button while attaching, but `uploadAttachmentTo()` wrapped a `FileReader` in a
  Promise that never settled if the file read errored or the `/api/attach` request
  threw — so the `await` never returned, `CREATING` stayed `true`, and the button
  stayed disabled until a page reload. It now has a `reader.onerror` handler and a
  `try/catch` around the upload, so the Promise always resolves and the button is
  always restored.
- **Staged image could change mid-submit.** `createFromCard()` read `PENDING_ATTACH`
  *after* the `/api/add` round-trip, so pasting, removing, or dropping an image
  during the (async) wait could attach the wrong image or none. The staged set is
  now snapshotted at submit time.

### Tests

- Added regression tests asserting the quick-add guards (re-entry lock, button
  disable/restore, in-flight label) and the attach Promise's always-settle paths
  (`reader.onerror`, `try/catch`, submit-time snapshot) are present in the served UI.

## [0.7.1] - 2026-06-03

### Fixed

- **Quick-add "Add" button looked dead with an image attached.** When a new
  to-do or project carries a staged image, the server has to discover the new
  item's UUID by polling Things' database (the URL Scheme doesn't return it),
  which can take several seconds on a large library. During that wait the button
  stayed enabled with no feedback, so it read as a no-op — and a second impatient
  click created a duplicate. The button now disables and shows "Adding…" /
  "Adding image…" while the request is in flight, and a re-entry guard blocks
  duplicate submits.
- **Silent failures in quick-add.** `createFromCard()` had no error handling, so
  a thrown `fetch` (or any exception) failed silently — the overlay just sat
  there with no message. It now surfaces the error in an alert and always
  restores the button state.
- Realigned `__version__` in `__init__.py` (had drifted to `0.2.0`) with the
  package version.

## [0.7.0] - 2026-05-26

### Added

- **Priority Levels** — a 2×2 grid (P1–P4) that ranks tasks by your *existing*
  Things tags, not a separate browser overlay. Available from the sidebar (over
  Today) and as a **view toggle** on any list, area, or project. Map real tags to
  each level (e.g. `🔴` → P1) in the ⚙ editor; a task lands at the first level
  whose tags it carries. Drag a task between levels and the mapped tag is written
  back to Things via the URL scheme (the old level tag is replaced in the same
  write). Read-only when `THINGS_AUTH_TOKEN` isn't set — it still shows what's
  already tagged. The tag→level map is stored in `board.json` (`priority_levels`),
  never in Things.
- **App-window mode** — `suur-things-mcp dashboard --app` (or the `open_dashboard`
  tool with `app=true`) opens the dashboard in a frameless Chromium app window
  (no tabs or address bar, its own Dock icon) instead of a browser tab. Prefers
  Chrome → Brave → Edge → Chromium → Vivaldi → Arc; falls back to a normal tab.
- **Drag a task onto a heading** — in a project, drop any task on a heading (e.g.
  "iOS App") to move it under that heading, via the URL Scheme's `heading` param.
  A "no heading" drop zone (it appears at the top only while you're dragging) pulls
  a task back out to the top of the project.
- **Linked repos on the project (and area) page** — open a project and its linked
  repos show right under the notes, with the same chips (open in editor / terminal /
  GitHub), a "🔗 repos" manager, and the git/GitHub pulse (commits/wk, last commit,
  open PRs) you'd see on a Kanban card — so you get them even when the project isn't
  on any board.
- **Areas roll up their projects' tasks** — selecting an area now shows the tasks
  living inside its projects, grouped by project, alongside the area's loose
  to-dos. Things only shows an area's loose to-dos; this makes an area a real
  overview of everything under it. A **"Project tasks"** pill in the header (next
  to the view switcher, shown for areas in every view) turns the roll-up off (back
  to project cards only); the choice is saved per area in `board.json`
  (`area_prefs`).
- **Image attachments** — Things can't store images, so attach them here instead.
  Drag, paste, or pick an image in a task's edit card and it shows inline in the
  dashboard. Bytes live on disk under `~/.config/suur-things-mcp/attachments/`;
  only metadata goes in `board.json`. With `THINGS_AUTH_TOKEN` set, a clickable
  `file://` reference is appended to the task's notes so the Things app shows it too.
  - New `attach_image(item_uuid, source_path, caption)` MCP tool so an agent can
    attach a chart/screenshot it generated; `get_item` now reports `attachments`.
  - Endpoints `POST /api/attach`, `GET /api/attachment`, `POST /api/detach` —
    the serve endpoint only returns files recorded in the overlay and rebuilds the
    path server-side, so it can't be used to read arbitrary files.
  - A task with an image shows an **image icon** next to the note icon in the list,
    so attachments are visible at a glance.
  - The Things note now reads **"🖼 Image attached: …"** (clearer that there's an
    image), and the append is idempotent (re-attaching won't duplicate the line).
  - **Creating a to-do now uses the same card as editing one** — the ＋ button opens
    the full edit card in a "new" mode (To-Do/Project toggle, notes, when/deadline/
    tags, and the 📎 attach tool). You can **attach an image while creating**: it's
    staged in the browser, then linked once the to-do exists (its new ID is resolved
    server-side, since the URL Scheme doesn't return it). Project notes also
    **linkify bare domains** now (e.g. `hrv.suur.io`), not just `https://` URLs.

> Note: attached images are local to this machine (plus wherever the config folder
> syncs). They are not in Things Cloud and won't appear on iOS.

## [0.4.2] - 2026-05-26

From early dashboard feedback.

### Fixed

- **Organize** no longer reports "no agent CLI found" when the dashboard is
  launched outside a shell (GUI/launchd/Things URL). It now resolves
  `claude`/`codex` via the login-shell PATH and runs them with that PATH.
- **Anytime/Someday** no longer render projects as (checkbox-less) task rows —
  built-in lists show to-dos only; projects stay in the sidebar.
- Tasks can now be **completed directly from the Matrix / Priority view**.

### Added

- ⌘K surfaces **New to-do / New project** as the first quick actions.
- Natural-language quick-add understands **relative dates** — "in 4 weeks",
  "in 3 days", "next week/month/year".

## [0.4.1] - 2026-05-25

### Security

Hardens the local dashboard's browser boundary. These are local-first issues:
they require the dashboard to be running and the user to load a malicious page
in the same browser. No data is ever exposed to the network.

- **Dashboard reads are now Host-checked.** Added `TrustedHostMiddleware` so any
  request whose `Host` isn't `127.0.0.1`/`localhost` is rejected — closes a
  DNS-rebinding path that could read task titles/notes and linked repo paths.
- **Cross-origin POSTs are properly blocked.** The origin guard now matches the
  full origin (scheme + host + port), not just the hostname. Previously a page
  served from a *different localhost port* could drive state-changing requests
  (config, repo links, open-in-editor, quick-add).
- **Auth token no longer leaks on errors.** The Things auth token is now redacted
  from URL-Scheme error/timeout messages, not only from success responses.
- **Organize agent runs without the token.** `THINGS_AUTH_TOKEN` is stripped from
  the environment of the spawned `claude`/`codex` CLI.

### Changed

- Pinned GitHub Actions to commit SHAs and added Dependabot; committed `uv.lock`
  for reproducible installs.
- Fixed invalid `\s`/`\d` escape sequences in the embedded dashboard JS.

If you installed 0.4.0 or 0.3.0, upgrade with `uv tool upgrade suur-things-mcp`
(or `pip install -U suur-things-mcp`).

## [0.4.0] - 2026-05-25

- Command palette (⌘K), day timeline view, and agent-driven workflows.

## [0.3.0] - 2026-05-25

- First public release.

[0.5.0]: https://github.com/artyomsklyarov/suur-things-mcp/releases/tag/v0.5.0
[0.4.2]: https://github.com/artyomsklyarov/suur-things-mcp/releases/tag/v0.4.2
[0.4.1]: https://github.com/artyomsklyarov/suur-things-mcp/releases/tag/v0.4.1
[0.4.0]: https://github.com/artyomsklyarov/suur-things-mcp/releases/tag/v0.4.0
[0.3.0]: https://github.com/artyomsklyarov/suur-things-mcp/releases/tag/v0.3.0
