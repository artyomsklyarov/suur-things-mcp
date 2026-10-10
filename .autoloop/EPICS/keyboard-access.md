# E01 — Keyboard access to existing workflows

Status: complete. No new product feature or data schema. No flag required: each milestone is a complete accessibility correction to existing controls.

Candidate scores (1-5, sum): keyboard access user value 5, product fit 5, feasibility 5, self-contained 5 = 20. Runner-up narrow-window layout 5/4/5/4 = 18. No accounts, dependencies, keys or human setup. Stable gate at start: 149 tests, lint/compile/offline builds green.

Spec: users can open, navigate and dismiss every existing dialog using keyboard, with named fields and focus returned to its trigger; background cannot receive focus. Existing click, autosave, reduced-motion and instant command palette behaviors stay intact. Users can reach sidebar destinations, filters, task cards/rows and completion actions with keyboard; controls expose purpose/state to assistive tech.

Milestones:
1. Dialog semantics, field labels, focus entry/trapping/return, topmost Escape handling, native close/complete buttons.
2. Keyboard navigation, expandable areas, task/filter controls and palette screen-reader state. Regression-test main flows; read screenshots in both themes/sizes.

Progress: milestone 1 in progress (iteration 7). Before: openOverlay/closeOverlay toggle CSS only; no modal roles, background inertness or focus containment. tests/test_dashboard_interactions.py now protects basic flows before edits.

Milestone 1 DONE iteration 7: all seven overlays named; labels; native close/complete; stacked focus lifecycle/topmost Escape, three new browser regressions. 152 tests green. No flags.

Milestone 2 DONE iteration 8: keyboard links, area expansion state/focus, filter buttons, task-card/row editing, completion checkbox, palette combobox/listbox with selected-option state, focus outlines. Two end-to-end browser regressions; 154 tests green. Core workflows keyboard-usable; advanced drag-based placement remains a future scope decision.
