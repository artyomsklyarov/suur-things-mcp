# Autoloop summary — 2026-10-10

SUUR Things MCP is a published-beta Python MCP server and local macOS dashboard for Things 3. It reads the Things SQLite database without writing to it, dispatches authenticated changes through the official URL Scheme, and stores boards, priorities, time blocks, links and attachments in a separate local JSON overlay. Its value is finding, reviewing and acting on familiar tasks through an agent or dashboard. This run preserved those boundaries, the existing visual language and motion behavior.

Completed **23 improvement iterations and 9 dream sessions** on `autoloop/2026-10-10`, with each iteration's changes/evidence committed locally. Stop condition 1 is met: every applicable dimension scores at least 4, no High-impact or ready backlog items remain, and the final dream produced nothing promotable. No push, release, deployment, service installation, paid model call, real Things mutation or external message occurred.

## Scorecard before → after

| Dimension | Before | After | Evidence / limit |
|---|---:|---:|---|
| Correctness | 4 | 4 | 113 → 238 passing tests; lint/compile/offline build green; live Things acceptance remains separate |
| Reliability | 3 | 4 | Lossless corrupt-config recovery, atomic concurrency, startup retry, stale-read guards, best-effort note boundary |
| Test coverage | 3 | 4 | 125 tests added; actual Chromium workflows and fixture/API/harness failures; no line-coverage percentage claimed |
| Code quality | 4 | 4 | Ruff green; existing compact frontend conventions retained, no broad formatting rewrite |
| Architecture | 4 | 4 | Read-only database / URL Scheme / overlay separation retained |
| Security | 3 | 4 | Attachment containment and input/scope checks; bounded regression evidence, not a comprehensive audit |
| Performance | 4 | 4 | Existing threaded reads/cursor behavior retained; no unsupported speed claim |
| UX | 3 | 4 | 390px main width 118 → 390px; menu/focus recovery, all-view 320/390/768px tests |
| UI | 3 | 4 | Both themes, narrow/desktop and empty/populated views inspected; readable shared tokens |
| Accessibility | 2 | 4 | Named dialogs, focus containment/return, native placement alternatives, checkbox state/contrast; not exhaustive conformance |
| Product completeness | 4 | 4 | Three complete local epics; real integration acceptance excluded |
| Docs / developer experience | 4 | 4 | Safe fixture/capture/recovery guide and zero-skip verification gate |
| SEO / discoverability | N/A | N/A | Local desktop software, not a public website |
| Content quality | N/A | N/A | Software repository |

Baseline fixture evidence: [orientation](artifacts/orientation.txt). The initial unseeded command had 104 passed and nine environment skips; the seeded baseline ran all 113.

Detailed evidence: [scorecard](SCORECARD.md), [holistic review at 10](artifacts/holistic-10.txt), [holistic review at 20](artifacts/holistic-20.txt), [final verification](artifacts/final-verification.txt). The one existing Starlette/httpx deprecation remains; no new warnings. Verification uses the working checkout **including** the ten preserved pre-existing dirty files; a clean branch checkout without that user work was not separately certified.

## Biggest improvements by mode

| Mode | Change | Before → after evidence |
|---|---|---|
| Fix | Contained attachment paths and serialized cap/metadata writes | Five path regressions; eight simultaneous uploads accept exactly the configured two. [path before](artifacts/iter-1-before.txt), [path after](artifacts/iter-1.txt), [concurrency](artifacts/iter-3.txt) |
| Fix | Config byte-preserving recovery and read-error fail-closed behavior | Invalid roots/UTF-8 get exclusive digest-named recovery copies; unreadable settings cannot be overwritten. [before](artifacts/iter-2-before.txt), [after](artifacts/iter-2.txt) |
| Fix | Organizer submitted-ID/tag boundaries; API malformed input/error envelopes; preference preservation | Out-of-scope/duplicate suggestions ignored; malformed requests preserve overlay; supported agent/models survive saves. [organizer](artifacts/iter-4.txt), [API](artifacts/iter-13.txt), [preferences](artifacts/iter-14.txt) |
| Fix | Startup recovery, standalone projects and stale navigation | Retry preserves UI/settings; project route resolves; five delayed responses cannot replace newer views. [startup](artifacts/iter-6.txt), [project](artifacts/iter-9.txt), [races](artifacts/iter-15.txt) |
| Fix | Successful uploads survive failed optional note sync | Three post-storage server errors reproduced → success response with `note_updated=false`, stored bytes/metadata retained; six regressions. [before](artifacts/iter-21-before.txt), [after](artifacts/iter-21.txt) |
| Safety net | Real browser flows, advanced drag behavior and gate integrity | 113 → 238 tests; intercepted mutations, preserved tags/overlay, zero-skip JUnit requirement. [browser](artifacts/iter-5.txt), [drag](artifacts/iter-17.txt), [false-green before](artifacts/iter-22-before.txt), [after](artifacts/iter-22.txt) |
| UX / UI | Compact layout and reachable navigation in split windows | Main width 118 → 390px at 390px; all views fit supported narrow widths. [before image](artifacts/baseline-settled/mobile-light.png), [after image](artifacts/iter-20-screens/mobile-light.png), [desktop](artifacts/iter-20-screens/desktop-light.png) |
| Accessibility | Keyboard/focus semantics, placement and explicit scheduling | Modal/sidebar/task/palette behavior protected; Matrix/Levels/Board native selects and Timeline dialog enabled. [controls](artifacts/iter-20-placement/mobile-matrix-dark.png), [scheduled dialog](artifacts/iter-20-slots/mobile-slot-dark.png), [tests](artifacts/iter-20.txt) |
| Accessibility | Shared text and checkbox colors measured in both themes | Sampled small-text minima light 2.48 → 4.86 and dark 3.19 → 4.93; checkbox unselected borders 1.715/2.632 → above 3 in tested states. [text measurements](artifacts/iter-12-ratios.txt), [checkbox before](artifacts/iter-20-before.txt), [after](artifacts/iter-20.txt) |
| Docs | Safe reproducible checks and recovery instructions | New [developer guide](../docs/DEVELOPMENT-VERIFICATION.md); existing README preserved with a [proposed insertion](proposed-edits/README-verification-addition.md) |

Final verification initially found a synthetic fixture mismatch: its cursor response omitted the real endpoint’s change cursor, causing unnecessary polls to reintroduce static incomplete data. Iteration 23 added a stable cursor and an unchanged-cursor regression; the original completion assertion was retained. [Failure evidence](artifacts/iter-23-before-full.txt), [stabilization gate](artifacts/iter-23.txt), [repeated focused checks](artifacts/iter-23-repeat.txt).

Final holistic visual pass read **32 individual synthetic screenshots** across List/Preferences/Trash, empty Project, Matrix, Levels, Board, Timeline and populated scheduling dialog. Both themes and desktop/narrow windows; all reports have no uncaught page errors. Board retains deliberate horizontal stage scrolling, stacked views vertical scrolling. No private task data was captured.

## Epics and flags

- [E01 keyboard access](EPICS/keyboard-access.md): complete, iterations 7–8; enabled directly, no flag.
- [E02 narrow windows](EPICS/narrow-window.md): complete, iterations 10–11; automatic at widths <=800px. `?compact=0` restores the previous fixed sidebar for diagnosis; no enablement needed.
- [E03 advanced placement](EPICS/advanced-placement.md): complete, iterations 17–20; default-enabled. `?placement=0` retains the prior placement controls for diagnosis. Matrix/Board/Timeline change only the local overlay; Levels retains authenticated tag updates.

No epic or incomplete feature flag remains active. Existing drag actions and features are retained.

## Dreams

The [dream journal](DREAMS.md) records nine sessions through all eight lenses plus a final first-impression review. Promoted and built: safe visual onboarding through fixture captures, narrow-window access, keyboard placement, successful-upload trust and a complete verification gate. Optional personal history, semantic search, audit/undo and sync concepts remain parked with concrete prerequisite decisions below. Project-timeline and warning-only time-budget ideas were rejected for insufficient demonstrated value, not blocked by invented permission requirements. The final dream yielded no new promotable/lucid work.

## NEEDS HUMAN DECISION — ready plans

These decisions are separate from the completed local backlog. See [reasoning](DECISIONS.md). No action or input is requested by this run.

| ID | Exact next change / acceptance plan |
|---|---|
| H01 | Review the ten files in `artifacts/preexisting-work.json` as the separate staleness-review change, run this fixture gate, and commit that work separately. All ten remain byte-identical and unstaged: [final hashes](artifacts/protected-final.json). |
| H02 | Choose a user-owned disposable task; record its original title/notes/tags/status, enable its existing Things token outside source, then verify create/update/complete via official URL Scheme and read-back timestamps. Retain the task/data and record actual outcomes; no cleanup deletion. |
| H03 | In a separate dependency change after H01, select a supported Starlette test-client setup/pins, update manifest/lock together, run full fixture/browser suite and confirm the existing deprecation disappears. Do not add a speculative dependency or raise Python requirements. |
| H04 | Review the local branch plus any separately committed H01 work; follow the repository's normal version/release procedure only with explicit publication authorization. No remote action has been taken. |
| H05 | Define audit retention/location/privacy, then specify an append-only record containing task UUID, proposed fields, selected fields, dispatch result and verified outcome. Add migration and synthetic read/write tests before persistent collection. |
| H07 | Choose acceptable local-model license/size and optional-dependency budget; benchmark fixture title/note search against the selected model in a dev-only prototype before indexing any personal data. |
| H09 | Define what an attention score means and retention/privacy policy; use synthetic staleness/repo timestamps for a dev-only joining prototype, then require explicit evidence before displaying a score over real tasks. |
| H10 | Define ontology fields, local model and indexing/storage boundaries; add migration/fixture tests before any local classifier or training/indexing of personal records. |
| H12 | Conduct permitted user research about return-after-absence needs; based on actual findings, prototype a dismissible local hint without guessed guilt or urgency. No contacts were made. |
| H13 | Choose user constraints and approved model/budget; use synthetic reviewed schedule proposals first, then opt into the existing review workflow before live model calls or URL Scheme changes. |
| H14 | Specify retention/export/deletion and encryption for personal history; build a synthetic local indexing demo after model/storage choices, before retaining or uploading any personal history. |
| H15 | Define compensating-undo retention/conflict policy; on a disposable task prove read-back and intervention detection so Undo cannot overwrite later user edits. Implement append-only before/after records and migration tests; never promise transactional Things writes. |
| H16 | Supply quarter goals and review rules; compare synthetic project proposals against a rubric first, then authorize any capped live model work. Do not dispatch unreviewed changes. |
| H17 | Approve model choices, monetary cap and privacy-safe fixture corpus; compare identical mocked proposals first, then run live organizer evaluation under that budget and rubric. |
| H18 | Choose on-device versus provider speech, privacy and accessible review behavior; use text fixtures first. Separately approve microphone permissions/configuration and any paid endpoint before audio capture. |
| H19 | For optional private personal sync, specify synthetic overlay conflicts and encryption/key recovery; choose account/backend/retention architecture before adding an opt-in provider. Team collaboration was rejected as a different product. |

H06/H08 are rejected, H11 is completed as E03; they are not pending human gates. Existing recovery copies, task data, features, sensitive configuration, manifests and user changes were preserved. No new dependency or minimum platform/language version change.

## Next run

Resume from `.autoloop/` and first verify the current checkout: `.venv/bin/python .autoloop/scripts/verify.py resumed-check`. Review H01 and live H02 evidence if separately authorized, then prioritize any reproduced new failures. Re-run visual captures when behavior changes. Do not add speculative history/model/sync features merely to keep the loop running.
