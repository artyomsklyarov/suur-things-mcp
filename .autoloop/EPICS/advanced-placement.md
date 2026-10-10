# E03 — Keyboard access to advanced placement

Status: active. Candidate score: user value 4, fit 5, feasibility 5, self-containment 5 = 19. Runner-up: timeline-only keyboard scheduling, 3/5/5/5 = 18; use that smaller slice if shared controls prove impractical. Stable full gate 199 tests. No accounts, paid work or dependencies.

Spec: preserve drag and click behavior while giving each advanced task/project a named keyboard edit/open/completion action and a native destination control. Board stages and matrix quadrants remain overlay-only. Priority Levels reuses the existing authenticated canonical-tag update. Timeline opens a named local slot dialog for explicit time/duration and unscheduling, with existing modal focus handling. New UI is preview-only behind `?placement=1` until all slices pass.

Milestones:
1. Safety net: protect board/matrix/level/timeline drag behavior with synthetic intercepted routes, including no-token level write refusal.
2. Native board-stage, matrix and level selectors; keyboard card actions; preserve focus after placement, guard async rerenders and restore UI on failure.
3. Timeline time/duration/unschedule dialog; inspect light/dark narrow/desktop views, then default-enable all completed controls with `?placement=0` diagnostic fallback.

Verification: full gate each slice; focused browser tests assert request scopes, unrelated tags and source records remain, no real URL Scheme/model execution. UI evidence before from iter-12-advanced, after new preview captures. No task-data deletion, migrations, feature removal or environment changes.

Milestone 1 DONE iteration 17: five browser tests cover board, matrix, level tag-preservation/no-token and timeline place/unschedule actions. All requests intercepted; unrelated priority/tags retained; 204 tests/full gate green. Existing actions preserved unchanged.
