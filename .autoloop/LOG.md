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

Iteration 12 commit: d1be10a.

## Iteration 13 — Fix
B10: validate config/link object and section/list shapes before mutation, reject non-string MIME, envelope config/item/board reads and attachment disk errors. Before: 18 targeted failures (iter-13-before.txt). After: 26 new regressions, 187 tests/full gate green (iter-13.txt); invalid payload tests assert saved bytes unchanged. Existing warning only. No real Things/model writes. Scores remain 4; dream due before next product iteration. Commit: pending iter 13.

Iteration 13 commit: f478c0b.

## Dream 4 — Dream
Steal-from-elsewhere lens, twelve ideas and two ambitious. Continue existing B11/B15/B12/B17; five built capabilities, one new parked undo/conflict plan H15 and three rejections. No code or new dependencies. Commit: pending dream 4.

Dream 4 commit: d0a8c50.

## Iteration 14 — Fix
B15: sanitizer preserves organizer agent/model, editor preference saves retain them. Before: two config regressions and one browser regression fail (iter-14-before.txt, iter-14-browser-before.txt). After: 194 tests/full gate green (iter-14.txt), invalid types ignored; no live agent call. Scores remain 4. Commit: pending iter 14.

Iteration 14 commit: b59ca4e.

## Iteration 15 — Fix
B11: one request generation per async view, synchronous About invalidates old reads, guard before data errors/content/global-list mutation. Before: five race regressions fail (iter-15-before.txt). After: 199 tests/full gate green (iter-15.txt). Scores stay 4; dream due. Commit: pending iter 15.

Iteration 15 commit: fe03c5e.

## Dream 5 — Dream
A-day-in-the-life lens, twelve ideas, two ambitious. Existing B17 decomposed into protect/place/schedule; B12 retained; three built, one parked and three rejected. No code. Commit: pending dream 5.

Dream 5 commit: e164d13.

## Iteration 16 — Docs
B12: standalone verification/recovery guide and proposed README insertion, preserving existing docs. Before: commands/limitations only in loop state and scattered tests; no consolidated recovery procedure. After: docs/DEVELOPMENT-VERIFICATION.md with commands exercised in prior/current artifacts, 199 tests/full gate green (iter-16.txt). No new tests for prose-only work. Eight-iteration dream cadence due. Commit: pending iter 16.

Iteration 16 commit: 05eba0a.

## Dream 6 — Dream
Remove-a-constraint lens at iteration 16, twelve ideas including two ambitious. Existing B17 prioritized, two existing/new paid or persistent-model plans parked, six scope/boundary/duplication ideas rejected, settings resilience already built. No code. Commit: pending dream 6.

Dream 6 commit: 41c3729.

## Iteration 17 — Safety net
E03 protection milestone: five existing drag workflows covered, including mapped-tag-only replacement, no-token refusal and overlay-only timeline changes. Before: 199 tests, no advanced drag workflow protection. After: 204 tests/full gate green (iter-17.txt). No product code, accounts or dependencies changed. Scores stay 4. Commit: pending iter 17.

Iteration 17 commit: 88bb5c2.

## Iteration 18 — Accessibility
E03 selectors/card keyboard actions protected and implemented behind ?placement=1. Before: four missing-control regressions fail (iter-18-before.txt; default locator timeout made this capture slower than needed, subsequent helper timeout 3s). After: 209 tests/full gate green (iter-18.txt), scoped requests/focus/failure/no-token/keyboard completion verified; twelve images read. First gate exposed an immediate visibility assertion before async edit loaded; it now waits for the same visible dialog. No assertion removed. Scores remain 4; dream due. Commit: pending iter 18.

Iteration 18 commit: 4ab7dad.

## Dream 7 — Dream
10x lens, twelve ideas with two ambitious; finish existing E03, five protected/built capabilities, three parked plans and three rejections. No code. Commit: pending dream 7.

Dream 7 commit: c148cfd.

## Iteration 19 — Accessibility
E03 timeline dialog, explicit time/duration and unscheduling; local section-only storage, failure retention, no stale navigation replacement, unchanged unrelated blocks. Before: four missing-dialog failures (iter-19-before.txt). After: 214 tests/full gate green (iter-19.txt); eight final images read. First gate found real focus loss: disabling the Save button moved focus to body before the return decision. Use still-visible dialog/trigger state, preserving escape/navigation behavior. Revised compact pool cap and native dark clock after visual inspection. Scores stay 4. Commit: pending iter 19.

Iteration 19 commit: c0db91d.

## Iteration 20 — Accessibility
E03 completed and default-enabled with placement=0 diagnostic fallback. Before: four terminal-state/control-boundary regressions and default-control test failed (iter-20-before.txt, iter-20-ui-before.txt). After: 223 tests/full gate green (iter-20.txt); 32 screenshots individually read, reports have no page errors, slot dialog fits 320/768px. Existing timeline drag test now waits for the overlay state, since scheduled cards are also visible; assertions retained. Capture import order corrected after first lint gate. Holistic review re-scored all dimensions, verified all ten original dirty files byte-identical, found B18/B19. Scores stay 4; dream due. Commit: pending iter 20.

Iteration 20 commit: df0670f.

## Dream 8 — Dream
Ten-years-from-now lens: twelve ideas, two ambitious. Promoted B18/B19, parked personal-history/sync/compensating-undo plans, rejected duplicate or ill-fitting expansions. No product code. Full fixture gate recorded in dream-8.txt. Commit: pending dream 8.

Dream 8 commit: f8dfef2.

## Iteration 21 — Fix
B18 fixes optional note-sync failures after durable upload. Before: three failures reproduced, existing URL Scheme failure already behaved correctly (iter-21-before.txt); success and duplicate-reference checks pass. After: six regressions, full gate 229 tests (iter-21.txt). Storage bytes/metadata retained exactly once, success response preserved with note_updated=false; all Things operations mocked. No UI/dependency/sensitive edits. Reliability remains 4. Commit: pending iter 21.
