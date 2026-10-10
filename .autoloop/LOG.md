# Append-only iteration log

## Orientation — 2026-10-10
Mode: Docs. Identified mature macOS MCP server/local dashboard; read completed motion plans and roadmap. Preserved ten dirty files with hashes. Created autoloop/2026-10-10; initial sandbox denied .git/sockets, authorized local escalation succeeded. Added disposable full verification/capture harnesses. Evidence: artifacts/orientation.txt (113 passed, zero skips; lint/compile/build green; one pre-existing deprecation), artifacts/baseline/*.png (all eight read), baseline-format.txt (11 existing nonformatted files). Seeded fixture safely replaces real data tests. No product edits. Commit: pending orientation.

Orientation commit: 9cccebd.

## Dream 1 — 2026-10-10
Mode: Dream. First-impression lens, 12 ideas including two ambitious; eight grounded promotions (one already in orientation), three parked plans, two rejections. No product code. Evidence: DREAMS.md. Commit: pending dream 1.

Dream 1 commit: b5a5ce6.

## Iteration 1 — Fix
B01: component-aware resolved containment and safe identifiers for upload, serve and detach. Before: five targeted regressions fail (iter-1-before.txt), including upload and deletion outside root. After: 118 tests green, no skips, lint/compile/build green (iter-1.txt). No new warning. Reviewed all eight baseline-settled images: dark contrast is correct after existing 120ms background transitions, so rejected B08 instead of changing correct styling. Capture harness now waits 250ms after theme changes. Security 3 -> 4. Commit: pending iter 1.

Iteration 1 commit: 75c714f.

## Iteration 2 — Fix
B02: non-object/invalid-UTF8 overlay recovery, immutable unique backups, fail-closed unreadable files and junk repo-list sanitization. Before: nine failures, eight passes (iter-2-before.txt). After: full gate 130 passed, lint/compile/offline builds green; unchanged baseline warning (iter-2.txt). Reliability improved within dimension, concurrency remains. Commit: pending iter 2.

Iteration 2 commit: 8098eb3.

## Iteration 3 — Fix
B03: atomic per-item upload cap and unique atomic config temp files. Before: both concurrency tests fail (iter-3-before.txt). After: 132 tests and full gate green (iter-3.txt), eight concurrent attempts accept exactly two and preserve their metadata/bytes; two direct saves no longer collide. Commit: pending iter 3.

Iteration 3 commit: d371051.

## Iteration 4 — Fix
B04: tolerate malformed tags, preserve fenced note text, scope and deduplicate suggestions to submitted tasks. Before: seven failures (iter-4-before.txt). After: 139 tests and full gate green (iter-4.txt); existing warning only. Four consecutive Fix iterations complete; next mode Safety net protects frontend before larger UX/accessibility changes. Commit: pending iter 4.

Iteration 4 commit: 731f388.

## Iteration 5 — Safety net
B05: fixture-driven Chromium navigation, Inbox empty-state/create, literal hostile titles in list/cards, palette keyboard and scoped preference-save tests. API requests fully intercepted. Before: five existing browser tests, no protected broad workflows. After: nine browser tests, 143 total and full gate green (iter-5.txt). New harness initially had a Playwright keyword-argument typo; fixed without weakening assertions before commit. Test coverage 3 -> 4. Commit: pending iter 5.

Iteration 5 commit: 112356f.

## Iteration 6 — Fix
B07: tolerate corrupt/blocked localStorage, keep tasks usable after config error, prevent overlay writes until settings load, and retry sidebar without deleting its DOM structure. Before evidence was recaptured against committed HTML after an initial parallel capture saw new code: five failures plus four exception-teardown errors (iter-6-before.txt). After: 149 tests/full gate green (iter-6.txt). All eight iter-6-screens images read; normal desktop unchanged, narrow clipping still tracked. Reliability 3 -> 4. Commit: pending iter 6.

Iteration 6 commit: a823c44.

## Iteration 7 — Accessibility
E01 milestone 1: seven named modal overlays, field labels, native close/complete buttons, focus entry/trapping/return and inert background with stacked topmost Escape. Before: three dialog tests fail (iter-7-before.txt). After: 152 tests and full gate green (iter-7.txt); eight screenshots read with no unintended normal-layout change. Accessibility 2 -> 3. Found arealess-project resolution gap while planning empty-state evidence, tracked B14. Commit: pending iter 7.

Iteration 7 commit: 2873a6e.

## Iteration 8 — Accessibility
E01 milestone 2 complete: sidebar links/area toggles, task edit/complete, filter keyboard controls and state; palette combobox/listbox selected options; visible focus. Before: two new tests fail (iter-8-before.txt). First edit script aborted before changing files on an unmatched source fragment; corrected and reran full gate. After: 154 tests/full gate green (iter-8.txt); all eight images read, established UI retained. Accessibility 3 -> 4. Dream due before next product iteration. Commit: pending iter 8.

Iteration 8 commit: fddcf99. Screenshot readback correction: initial tool forwarding requested an unsupported low-detail setting and omitted images; all eight were immediately forwarded again at supported detail and inspected after the commit. No visual regression found.

## Dream 2 — 2026-10-10
Mode: Dream. Data-dream lens, 12 ideas, two ambitious; four grounded promotions (three existing backlog items), two already built, three parked plans and three rejections. No product code. Commit: pending dream 2.

Dream 2 commit: 575066c.

## Iteration 9 — Fix
B14: resolve standalone projects after area lookup, preserving nested/builtin behavior. Before: resolver returns null (iter-9-before.txt). After: 155 tests/full gate green (iter-9.txt), independent project URL/title are correct. Four actual empty-project screenshots read (iter-9-screens); mobile clipping remains. Commit: pending iter 9.

Iteration 9 commit: 4d371ac.

## Iteration 10 — UX
E02 milestone 1: compact navigation and full-width list/header behind ?compact=1; desktop preserved. Before: 390px viewport has 118px main (iter-10-before.txt). After: 390px main with usable view buttons/menu focus and Escape; 156 tests/full gate green (iter-10.txt), all eight preview/desktop images read. Mandatory holistic review artifacts/holistic-10.txt: all ten protected files unchanged, dimensions rescored and backlog re-ranked. No integer score improvement while flag incomplete; dream due. Commit: pending iter 10.

Iteration 10 commit: cfafaec.

## Dream 3 — 2026-10-10
Mode: Dream. Emotion lens after two unchanged integer scores; 12 ideas including two ambitious. Continue E02, promote measured contrast B16 and feasible keyboard-placement B17, three already built, three parked and three rejected. H11 corrected to feasible backlog work instead of an invented human gate. No code. Commit: pending dream 3.

Dream 3 commit: 7161021.

## Iteration 11 — UI
E02 complete: enable compact layout automatically, stack advanced pools/grids/calendar, align filter/header spacing. Before: three viewport regressions fail (iter-11-before.txt). After: 159 tests/full gate green (iter-11.txt), 320/390/768px all views and desktop resize pass. All twenty screenshots inspected (iter-11-screens, iter-11-empty, iter-11-advanced), no page errors; a mistaken screenshot filename was corrected with actual file inventory. UX/UI 3 -> 4. Optional ?compact=0 fallback retained. Commit: pending iter 11.

Iteration 11 commit: 3ed5b28.

## Iteration 12 — Accessibility
B16: measured and fixed text/control colors in both themes. Before: two real contrast failures (iter-12-before.txt), minimum 2.48 light/3.19 dark; initial test selector/cardinality mistakes corrected before recording this baseline. After: minimum 4.86/4.93 (iter-12-ratios.txt), 161 tests/full gate green (iter-12.txt). All sixteen screenshots inspected. First gate found missing strict zip; next found 4.494 below threshold plus a resize test waiting on an already-true sidebar condition. Darkened light muted further and waited for both inert states, without relaxing thresholds/assertions. Scores remain 4. Commit: pending iter 12.
