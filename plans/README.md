# Motion plans — SUUR Things dashboard

Written by the `improve-animations` audit (commit 60d36f4, post-frontend-
extraction). Headline finding: the dashboard has **zero motion of any kind**
(no `transition`, `@keyframes`, or easing in the file) while imitating
Things 3, whose feel depends on calm, functional motion. Everything here is
additive; each plan is self-contained and executable by any agent.

| # | Plan | Severity | Status |
|---|------|----------|--------|
| 000 | [Motion foundation: tokens, reduced-motion, animatable overlays](000-motion-foundation.md) | HIGH | DONE |
| 001 | [Overlay panel entrances; ⌘K stays instant](001-overlay-entrances.md) | HIGH | DONE |
| 002 | [The checkoff moment](002-checkoff-moment.md) | HIGH | DONE |
| 003 | [Press feedback and eased hovers](003-press-hover-feedback.md) | MEDIUM | DONE |
| 004 | [Disclosures: area collapse, edit-card editors, filter bar](004-disclosures-and-reveals.md) | MEDIUM | DONE |
| 005 | [Content transitions: navigation, loading states](005-content-transitions.md) | MEDIUM | DONE |
| 006 | [Drag-and-drop feel: lift, live targets, settle](006-drag-and-drop-feel.md) | MEDIUM | DONE |

All seven plans were executed and verified (real-Chromium pass, zero console/CSP
errors) on 2026-07-12.

## Execution order & dependencies

**000 first — everything depends on it** (tokens, the overlay
display→visibility conversion, the reduced-motion scaffold). After that:
001 → 002 → 003 are the highest-leverage trio (most-used surfaces). 004–006
are independent of each other and can run in any order or in parallel
worktrees.

## Deliberate non-animations (do not "fix")

- **⌘K command palette**: keyboard-frequency surface → no animation, ever
  (001 encodes the exemption).
- **Silent 25s auto-refresh**: must never animate (005 encodes the gate).
- **Completed rows lingering in lists**: product behavior, not a missing exit.
- **Modal transform-origin center**: correct for centered modals.

## Not planned (LOW polish, revisit after the above ship)

- Theme-toggle color crossfade (~150ms on body/panels only — never `*`).
- Progress-ring sweep on value change (rings are rebuilt via innerHTML; needs
  a keyed-update refactor first).
- 30–80ms stagger on board-card entrances (decorative; only if it never
  delays interaction).
- FLIP reflow of sibling cards after a drop (worthwhile, but a project).
