# SUUR Things MCP — development and release status

Updated: 2026-10-10. This is the current-state handoff. Read [CONTEXT.MD](CONTEXT.MD) for product intent, [SPEC.MD](SPEC.MD) for contracts, [TODO.MD](TODO.MD) for user actions and [PLAN.MD](PLAN.MD) for unfinished engineering work.

## Current release position

| Layer | Verified state |
|---|---|
| Public repository | `artyomsklyarov/suur-things-mcp`, PUBLIC, default branch `main` |
| Public GitHub release at preparation start | `v0.9.0`; 0.10.0 not yet released |
| Fresh PyPI metadata at preparation start | 0.9.0; no 0.10.0 release/files existed |
| Local source/version | 0.10.1, single-sourced in `__init__.py`; metadata 2.4 packaging correction, all 0.10.0 functionality retained |
| Working branch | `release/0.10.1`; full update merged through PR #53 at `bfbb51c` |
| Local verification checkpoint | 238 passing tests, zero skips; Ruff, compile and offline wheel/sdist green |
| New publication authorization | User explicitly requested committing the full update to GitHub and releasing a new version on 2026-10-10 |
| New release execution | Full update on main and GitHub v0.10.0 public; PyPI upload failed before transfer. Patch 0.10.1 prepared for metadata compatibility |

0.10.0 already existed in uncommitted source and was initially unpublished. Its GitHub release is now public, but its PyPI job rejected metadata 2.5 before uploading. The patch release is 0.10.1, explicitly using metadata 2.4 and preserving the public 0.10.0 checkpoint. Changelog dates reflect 2026-10-10. GitHub publication triggers the existing PyPI workflow; no publishing credentials or workflow permissions are being added.

The earlier autoloop explicitly avoided remote publication and left ten pre-existing dirty files byte-identical. That was correct for that task. The current user instruction authorizes reviewing/committing that existing update and public release. `.autoloop/SUMMARY.md` and its protected-file hashes are historical receipts, not assertions that those files must remain uncommitted forever.

## Implemented product surface

| Area | Implemented | Verification boundary |
|---|---|---|
| MCP reads | Built-in lists, search/filter, structure/detail, compact cards, overview | Synthetic DB/query/tool tests; not a complete live schema-version certification |
| MCP writes | Create/update/project/checklist/complete/cancel/schedule, batch and navigation | URL generation/auth/redaction/mocks; current release not accepted against real disposable tasks |
| Staleness | `stale_review`, age/idle card fields, `stale_sweep` prompt | Fixture thresholds/cohorts/disjointness/histogram/limits/read-only tests; edge cases and large live backlog remain partial |
| Dashboard lists | Grouping, overdue/empty states, editing, tag filters, palette, multi-select/context actions | Real Chromium with intercepted requests and fixture API coverage |
| Matrix | Shared local quadrants, drag and native destination selectors | Scoped overlay saves, focus/failure and drag tests |
| Levels | Tag mapping, preserved unrelated tags, native selectors/drag, no-token refusal | Mocked canonical writes; real Things tag acceptance pending |
| Cards | Link/YouTube tiles and task actions | Local rendering/browser behavior; external thumbnail availability not guaranteed |
| Boards | Project/area cards, stages/scope/settings, links/progress/pulse | Overlay/browser/API tests; real editor/terminal/gh integration not exercised in the loop |
| Timeline | Day grid, drag, explicit time/duration/change/unschedule dialog | Local overlay and browser validation/focus/navigation tests |
| Images | Local attachment metadata/files, caps/containment, best-effort note reference | Temp-file/API/concurrency tests; cross-machine portability and live Things note reference pending |
| Organizer | Claude/Codex selection, job cap/dedupe, proposal parsing/review/apply | Process mocked; live account/model quality/cost/privacy not accepted |
| Desktop lifecycle | App-mode/browser fallback, instance reuse, preferred port, launchd commands | Unit/API behavior; real login-agent restart/upgrade acceptance not run |
| Accessibility/layout | Dialog focus, keyboard core/advanced actions, compact defaults, measured colors | Browser and sampled contrast checks; not exhaustive assistive-technology conformance |

## What the autonomous run completed

23 improvement iterations, nine dream sessions and three completed epics. Every improvement checkpoint was committed locally. All applicable bounded health scores reached 4/5; no High-impact or ready loop backlog remained after the final dream. Full evidence is in [.autoloop/SUMMARY.md](.autoloop/SUMMARY.md), [LOG](.autoloop/LOG.md) and the artifact files linked there.

### Safety and reliability

- Attachment identifiers/MIME/path containment use full matches and resolved path components; symlink escapes reject without unsafe detach/data loss.
- Corrupt config handling preserves distinct original byte payloads using digest-named exclusive recovery copies. Invalid UTF-8/non-object roots are handled; read I/O errors fail closed.
- Exclusive atomic temp files avoid concurrent same-process temp-name collisions. Attachment cap checking and metadata/file changes share the existing cross-process lock.
- Organizer outputs normalize malformed tags and reject out-of-submission/duplicate UUID suggestions. Fenced JSON contents do not lose legitimate notes.
- Malformed API roots/section/list types reject before overlay replacement; read/storage failures use structured envelopes.
- Supported organizer preferences survive normal saves and editor/terminal preferences updates.
- Optional Things note synchronization cannot turn an already saved image into a false failed upload.

### Dashboard correctness and UX

- Startup tolerates blocked/corrupt cosmetic localStorage; settings failure offers retry and prevents premature overlay writes. Sidebar recovery preserves its structural container.
- Arealess project hashes resolve, including empty standalone projects.
- Async list/board/matrix/levels responses cannot replace newer navigation or mutate the new view's list state.
- At 390px, the main content width increased from 118px to 390px. All five task views are exercised at 320/390/768px and desktop restoration.
- Quiet polling, immediate palette and reduced-motion behavior were preserved.

### Accessibility

- Named/labeled dialogs with stacked focus entry/trap/return, inert background and topmost Escape behavior.
- Keyboard sidebar/area expansion, filters, task edit/completion and palette selection semantics.
- Shared theme colors improve measured small-text minima: light 2.48 → 4.86 and dark 3.19 → 4.93 in the sampled controls. This is sample evidence, not a comprehensive audit.
- Matrix/Levels/Board selectors plus Timeline Schedule/change/unschedule controls provide alternatives to drag. Pending/failing writes preserve state and avoid stale navigation replacement.
- Completed/canceled priority cards expose checked/disabled completion semantics. Measured checkbox boundaries meet the test's threshold in both themes and selected/unselected states.

### Test and documentation foundation

- 113 seeded baseline tests → 238 passing tests: 125 additional tests, including actual Chromium interactions, API/storage failures and concurrency.
- Strict fixture harness checks a valid JUnit report with executed tests and zero skips before building.
- Safe screenshot tooling uses disposable fixtures, both themes and ephemeral ports.
- New recovery/developer verification guide exists; this release adds the five root documents and updates public-facing release documentation.
- The initial final gate found a browser fixture cursor mismatch. A stable real-shaped cursor and unchanged-cursor regression fixed it without weakening the original completion assertion. Three focused repetitions and a second complete gate passed.

## Epics and flags

| Epic | Status | Enablement |
|---|---|---|
| E01 keyboard/core dialogs, iterations 7–8 | Complete | Enabled directly |
| E02 narrow windows, iterations 10–11 | Complete | Automatic <=800px; `?compact=0` diagnostic fallback |
| E03 advanced placement, iterations 17–20 | Complete | Default enabled; `?placement=0` diagnostic fallback |

No incomplete feature epic remains active. Diagnostic fallbacks preserve prior behavior; they are not required feature-enablement steps. Drag and existing user actions are retained.

## Done in source, not fully accepted

### Real task mutations

No live Things create/update/complete/cancel/batch was executed during the autonomous run or documentation preparation. MCP stamp observation is coarse and can be absent if the pre-write DB read fails. Dashboard success and batch success generally mean dispatch, not per-field/per-item acceptance. A user-owned disposable task and explicit test scope are still needed. Release publication does not close this gap.

### Staleness review

The main path is implemented and tested with backdated opt-in fixture records. Current `clusters` groups by project title, so duplicate titles can combine summaries. The histogram does not separately expose unknown timestamps. The “dead project” SQL checks open children without restricting child kind to to-dos; a heading-only project needs a regression/design correction. Live WAL/snapshot freshness and large dataset performance were not measured. These limitations are planned follow-ups, not reasons to claim the whole feature is absent.

The release preparation makes prompt language nonjudgmental: old timestamps do not infer motive/value, capped samples are not entire cohorts, leaving unchanged is valid, and exact lists need explicit approval before batch changes. Prompt text remains guidance for a connected agent, not an enforcement layer that can guarantee every client obeys it.

### Security and agent sandboxing

Host/origin/CSP/escaping/redaction/containment are implemented and tested. This is not a comprehensive penetration test. Local processes without browser headers can call the loopback API. Claude's no-tool/no-MCP configuration differs from Codex's best-effort read-only sandbox. Provider-auth exceptions intentionally remain in the organizer environment. Do not repeat historical blanket “agent cannot be injected” claims as a verified guarantee.

### Accessibility, compatibility and lifecycle

Screenshots and real-browser checks cover named flows and selected sizes/themes. No full VoiceOver/manual keyboard/zoom audit or broad macOS/browser/Python/Things compatibility matrix has been completed. Linux CI proves fixture behavior, not macOS launch/app/service integration. Login-agent install/restart, real repository launch tools and in-place package upgrade acceptance remain unverified for this release.

### Dependency warning

One existing Starlette TestClient/httpx deprecation remains. Tests pass; it was not silenced or resolved through speculative dependency changes. Dependabot has proposals, but none are included merely because they exist. Updating the MCP/Starlette/test-client stack needs a separate compatibility review and gate.

## Current evidence and commands

- Last autonomous complete gate: [.autoloop/artifacts/final-verification.txt](.autoloop/artifacts/final-verification.txt), 238 passed, zero skips; lint/compile/offline build passed.
- Last holistic review: [.autoloop/artifacts/holistic-20.txt](.autoloop/artifacts/holistic-20.txt), 32 individually read synthetic images.
- Stabilization: [original failed closeout](.autoloop/artifacts/iter-23-before-full.txt), [fixed gate](.autoloop/artifacts/iter-23.txt), [three repetitions](.autoloop/artifacts/iter-23-repeat.txt).
- Release-specific complete gate: [.autoloop/artifacts/release-0.10.0.txt](.autoloop/artifacts/release-0.10.0.txt), 238 passed/zero skips, unchanged one deprecation; package inspection in [release verification](docs/releases/0.10.0/VERIFICATION.md).

```sh
.venv/bin/python .autoloop/scripts/verify.py release-0.10.1
.venv/bin/python .autoloop/scripts/capture.py release-screens
uv build --offline
```

Build output alone is not a release. GitHub merge, GitHub release workflow, PyPI metadata and installable distribution files must each be verified. Release receipts below are updated only after the corresponding action succeeds.

## Publication receipts

- Full-update commit: `3a42e1c1557bca0738dbf6a284ef24ef16b428f8`.
- [PR #53](https://github.com/artyomsklyarov/suur-things-mcp/pull/53) merged normally at `bfbb51cec06e898ccb9b64747d442a9f8733e002` on 2026-10-10.
- [Required CI](https://github.com/artyomsklyarov/suur-things-mcp/actions/runs/38094162353) passed: 229 passed, nine environment-dependent skips, one test-client warning. The complete local fixture gate separately passed all 238 without skips. Existing setup-uv also emits a Node 20 migration warning on GitHub; no action/config upgrade is included here.
- [GitHub v0.10.0](https://github.com/artyomsklyarov/suur-things-mcp/releases/tag/v0.10.0) published at that merge commit, 2026-10-10 23:13:59 UTC.
- [0.10.0 PyPI job](https://github.com/artyomsklyarov/suur-things-mcp/actions/runs/38094300758) failed at metadata validation: `'2.5' is not a valid metadata version`. Fresh 0.10.0 registry metadata returned 404; it is not an installable PyPI release.
- [0.10.1 full local gate](.autoloop/artifacts/release-0.10.1.txt): 238 passed, zero skips, unchanged test-client warning, Ruff/compile/build and lock consistency green. Both builds explicitly emit metadata 2.4. Patch CI, merge, release and public PyPI verification remain pending; publication is not inferred from local builds.
