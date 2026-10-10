# E03 — Keyboard access to advanced placement

Status: complete. Candidate score: user value 4, fit 5, feasibility 5, self-containment 5 = 19. Runner-up: timeline-only keyboard scheduling, 3/5/5/5 = 18; use that smaller slice if shared controls prove impractical. Stable full gate 199 tests. No accounts, paid work or dependencies.

Spec: preserve drag and click behavior while giving each advanced task/project a named keyboard edit/open/completion action and a native destination control. Board stages and matrix quadrants remain overlay-only. Priority Levels reuses the existing authenticated canonical-tag update. Timeline opens a named local slot dialog for explicit time/duration and unscheduling, with existing modal focus handling. New UI is default-enabled after milestone 4; `?placement=0` provides a diagnostic fallback.

Milestones:
1. Safety net: protect board/matrix/level/timeline drag behavior with synthetic intercepted routes, including no-token level write refusal.
2. Native board-stage, matrix and level selectors; keyboard card actions; preserve focus after placement, guard async rerenders and restore UI on failure.
3. Timeline time/duration/unschedule dialog; inspect light/dark narrow/desktop views, retain preview until the final whole-view check.
4. Whole-view/viewport verification and holistic review, default-enable with `?placement=0` diagnostic fallback.

Verification: full gate each slice; focused browser tests assert request scopes, unrelated tags and source records remain, no real URL Scheme/model execution. UI evidence before from iter-12-advanced, after new preview captures. No task-data deletion, migrations, feature removal or environment changes.

Milestone 1 DONE iteration 17: five browser tests cover board, matrix, level tag-preservation/no-token and timeline place/unschedule actions. All requests intercepted; unrelated priority/tags retained; 204 tests/full gate green. Existing actions preserved unchanged.

Milestone 2 DONE iteration 18: native stage/quadrant/level selectors, keyboard card edit/open/complete, scoped section saves, focus restoration, no-auth level disable and failed-save retention. Five new regressions; 209 tests green. Twelve rendered preview screenshots read (iter-18-screens); native controls fit both themes/windows. Small pools retain internal scrolling and boards horizontal scrolling. Still ?placement=1 until timeline + final checks complete.

Milestone 3 DONE iteration 19: local slot dialog with native time/duration, explicit unscheduling, validation, preserved unrelated blocks, failed-save retention, stale-navigation guard and focus return. Five new regressions, 214 tests green. Eight final timeline/dialog screenshots read. Increased preview compact pool cap to 360px after screenshots showed second action partially clipped; native dark clock now visible. Still preview until whole-view milestone 4.

Milestone 4 DONE iteration 20: default enablement, terminal-state checkbox semantics and measured control boundaries. Nine new tests; 223 pass, builds/lint green. Thirty-two screenshots read, all reports free of page exceptions; scheduled slot dialog also fits 320/768px. Holistic rescore and protected-file hashes recorded. No new dependencies.
