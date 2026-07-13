# 003 — Press feedback and eased hovers on all controls

- **Status**: DONE
- **Commit**: 60d36f4 (+ uncommitted frontend extraction to `src/suur_things_mcp/static/index.html`)
- **Severity**: MEDIUM
- **Category**: Physicality & origin
- **Estimated scope**: 1 file, ~12 lines of CSS
- **Depends on**: plan 000 (tokens)

## Problem

No pressable element has `:active` feedback, and every hover state snaps
between colors instantly. Buttons feel like screenshots. Examples of current
hover-only, transition-less rules:

```css
/* src/suur_things_mcp/static/index.html:36 — current */
.iconbtn:hover { background:var(--row-hover); }
/* :322 */
.btn:hover { background:var(--row-hover); } .btn.primary { … }
/* :136-137 — view-toggle segments */
.vt { border:0; background:transparent; …; cursor:pointer; }
.vt.on { background:var(--main-bg); …; box-shadow:0 1px 2px rgba(0,0,0,.08); }
```

## Target

One shared rule set — press scale at 0.97 (subtle band 0.95–0.98), 160ms
ease-out; hovers ease over ~120ms; hover motion gated to real pointers:

```css
/* pressables: shared press + hover easing */
.btn, .iconbtn, .vt, .chip, .ec-tool, .rb, .cmdk-btn {
  transition: background var(--dur-fast) ease, color var(--dur-fast) ease,
              border-color var(--dur-fast) ease, transform 160ms var(--ease-out);
}
@media (hover: hover) and (pointer: fine) {
  .btn:active, .iconbtn:active, .vt:active, .chip:active, .ec-tool:active, .rb:active { transform: scale(0.97); }
}
/* rows/cards: color-only hover easing (hit dozens of times a day — keep it barely-there) */
.row, .nav-item, .project, .area-head, .projcard, .taskcard, .ck-row {
  transition: background var(--dur-fast) ease; }
```

Reduced motion (append to plan-000 block):

```css
.btn:active, .iconbtn:active, .vt:active, .chip:active, .ec-tool:active, .rb:active { transform: none; }
```

## Repo conventions to follow

- Selectors group multiple classes per rule (see `:63`
  `.nav-item:hover, .project:hover { … }`) — extend that style, don't write
  one rule per class.
- Do not introduce new class names; hang everything on existing classes.

## Steps

1. Add the two shared `transition` rules near the `.btn` definitions (~:322).
2. Add the `:active` rule inside the `@media (hover:hover) and (pointer:fine)`
   query.
3. Append the reduced-motion override.

## Boundaries

- Do NOT change any colors, paddings, or layout — transitions and `:active`
  transform only.
- Do NOT add hover scale/lift to rows or cards (frequency rule: tens of
  times/day → color ease only, no movement).
- Do NOT touch the drag-and-drop `.dragging`/`.drop` classes (plan 006).

## Verification

- **Mechanical**: `uv run pytest -q` — all pass; `uv run ruff check .` clean.
- **Feel check**:
  - Click-and-hold any toolbar button: it compresses slightly (~0.97) and
    springs back on release; releasing mid-press retargets smoothly (CSS
    transitions are interruptible — confirm no restart-from-zero).
  - Hover a sidebar row: background eases in ~120ms; moving the pointer fast
    down the list never smears or lags.
  - View toggle List↔Matrix: the segment press feels tactile; the `.on` state
    change itself stays instant (selection is state, not motion).
- **Done when**: every button press has physical feedback and no hover
  anywhere snaps.
