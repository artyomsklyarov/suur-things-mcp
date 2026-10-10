# E02 — Usable narrow dashboard windows

Status: active. Candidate score: user value 5, fit 4, feasibility 5, self-containment 5 = 19. Runner-up stale-navigation guard 4/5/5/5 = 19, lower direct user value. Stable baseline: 155 tests/full gate green. All dependencies already present.

Spec: in windows <=800px, task content uses the available width, navigation opens from an explicit menu button with keyboard dismissal, the list view switcher remains reachable, and existing card/matrix/levels/timeline/board views retain their data and actions. Desktop styling/motion stays consistent.

Milestones:
1. Menu, overlay/focus lifecycle, compact header/list layout; dev-only `?compact=1` until all view checks complete.
2. Complete other view layouts at 320/390/768px, prove resize/reduced-motion/empty and populated flows, then enable automatically (optional `?compact=0` fallback retained).

Before: 390px viewport reserves 272px for sidebar and leaves 118px main content; screenshots baseline-settled and iter-9-screens show clipped titles/actions. No setup/accounts/data migration.

Milestone 1 DONE iteration 10: dev-only compact sidebar/menu, focus/Escape/navigation close, wrapping header, full-width main. 390px main 118 -> 390. One browser regression, full suite 156 tests. Normal desktop and preview screenshots read; milestone 2 must finish grid/timeline layouts before default enablement.
