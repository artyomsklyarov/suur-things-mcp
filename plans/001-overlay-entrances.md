# 001 — Overlay panel entrances (edit card + panels); ⌘K stays instant

- **Status**: DONE
- **Commit**: 60d36f4 (+ uncommitted frontend extraction to `src/suur_things_mcp/static/index.html`)
- **Severity**: HIGH
- **Category**: Missed opportunities / Physicality & origin
- **Estimated scope**: 1 file, ~15 lines of CSS
- **Depends on**: plan 000 (tokens + animatable overlays)

## Problem

The edit card (`.editcard`) and the settings/prefs/repos/levelmap/organize
panels (`.panel`) appear fully-formed the instant `.show` lands — the single
most-used surface in the app (opening a task) is the most jarring. Things 3
presents its edit card with a soft, fast settle.

The command palette (`#cmdk`) is the exception: it's keyboard-summoned
(⌘K, used constantly). Per the frequency rule, command palettes get **no
animation** (Raycast behavior) — this plan must explicitly exempt it.

Current state after plan 000: the backdrop fades but the panel inside doesn't
move — a pure fade with no transform reads as a flicker, not an entrance.

## Target

Panels scale from 0.97 with a 4px rise, only while their overlay is off →
never from `scale(0)`:

```css
/* target — place right after the .overlay rules from plan 000 */
.overlay > .editcard, .overlay > .panel {
  transform: scale(0.97) translateY(4px);
  transition: transform var(--dur-med) var(--ease-out);
}
.overlay.show > .editcard, .overlay.show > .panel { transform: none; }

/* ⌘K: keyboard-frequency surface — instant, always */
#cmdk, #cmdk.show { transition: none; }
#cmdk > .ck-panel { transform: none !important; transition: none !important; }
```

Reduced motion (append selectors to the plan-000 media block):

```css
.overlay > .editcard, .overlay > .panel { transform: none; transition: none; }
```

## Repo conventions to follow

- Overlay markup: `<div class="overlay" id="edit-overlay"><div class="editcard">…`
  (`src/suur_things_mcp/static/index.html:377-378`) and
  `<div class="overlay" id="prefs-overlay"><div class="panel">…` (:439-440).
  `#cmdk` wraps `.ck-panel` (:431-432). Selectors above already match all of
  them — do not enumerate per-overlay rules.
- Tokens from plan 000: `--ease-out`, `--dur-med`.

## Steps

1. Add the target CSS after the `.overlay.show` rule.
2. Append the reduced-motion selectors to the existing
   `@media (prefers-reduced-motion: reduce)` block.
3. Verify `autoGrow()` still measures the title field correctly: the quick-add
   card's `#f-title` height is computed on open (the v0.8.5 "invisible title
   field" bug). The transform must not affect it — transforms don't change
   `scrollHeight`, but confirm in the feel check.

## Boundaries

- Do NOT animate `#cmdk` (the exemption is the point).
- Do NOT touch JS.
- Do NOT add entrance motion to `.ec-editor` sub-panels (When/Deadline/Tags
  rows inside the edit card) — they're covered by plan 004.
- If the cited structure has drifted, STOP and report.

## Verification

- **Mechanical**: `uv run pytest -q` — all pass (browser tests exercise the
  quick-add card end-to-end).
- **Feel check** (fresh foreground dashboard, not the :8765 service):
  - Click a task: the card settles in — a fast, small scale+rise, no bounce.
  - DevTools Animations panel at 10% speed: the card never starts from
    invisible-small (`scale(0.97)`, not `scale(0)`), origin center (correct
    for a modal — do not "fix" it).
  - ⌘K: opens with ZERO animation. Spam ⌘K/Escape: never lags, never blinks.
  - Type a title in ＋ quick-add: the title field is visible and grows.
  - Reduced-motion emulation: panels appear without movement, backdrop still
    fades quickly.
- **Done when**: every panel eases in calmly, ⌘K is instant, tests pass.
