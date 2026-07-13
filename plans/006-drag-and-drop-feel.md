# 006 — Drag-and-drop feel: lift, live targets, settle

- **Status**: DONE
- **Commit**: 60d36f4 (+ uncommitted frontend extraction to `src/suur_things_mcp/static/index.html`)
- **Severity**: MEDIUM
- **Category**: Interruptibility / Physicality
- **Estimated scope**: 1 file, ~20 lines CSS + ~8 lines JS
- **Depends on**: plan 000 (tokens)

## Problem

Dragging is the dashboard's flagship interaction (board columns, Eisenhower
quadrants, priority levels, timeline blocks, sidebar reschedule targets), and
every part of it snaps:

```css
/* src/suur_things_mcp/static/index.html — current */
.card.dragging { opacity:.4; }            /* :259 — snaps to ghost */
.tl-block.dragging { opacity:.4; }        /* :189 */
.pcard.dragging { opacity:.4; }           /* :287 */
.col-edit.dragging { opacity:.4; }        /* :326 */
.grp-head.drop { outline:2px dashed var(--accent); outline-offset:3px; … }  /* :96 — snaps on */
.heading-dropzone.drop { border-color:var(--accent); … }                     /* :100 */
```

Drop targets (`.drop` class, added/removed in dragover/dragleave handlers at
`:936`, `:989`, `:1132`, `:1190`, `:1248`) blink hard as the pointer crosses
column boundaries, and a dropped card lands with zero acknowledgment.

HTML5 native DnD constrains us (the browser owns the drag image), but the
source element, the targets, and the landing are ours.

## Target

```css
/* lift + ghost: ease in/out of the dragging state */
.card, .tl-block, .pcard, .col-edit { transition: opacity var(--dur-fast) ease, transform var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) ease; }
.card.dragging, .tl-block.dragging, .pcard.dragging, .col-edit.dragging { opacity:.4; transform: scale(0.98); }

/* drop targets breathe instead of blinking */
.grp-head, .heading-dropzone, .col, .quad, .lvl-band { transition: background var(--dur-fast) ease, border-color var(--dur-fast) ease, outline-color var(--dur-fast) ease; }

/* landing acknowledgment — one-shot */
.dropped { animation: settle 180ms var(--ease-out); }
@keyframes settle { from { transform: scale(1.02); } }
```

(Adjust the drop-target selector list to the real container classes found in
the dragover handlers — verify each of the five sites at `:936`, `:989`,
`:1132`, `:1190`, `:1248` and use the exact element the `.drop` class lands on.)

JS — after each successful drop handler moves a card into its new column/
quadrant/band, tag it:

```js
card.classList.add("dropped");
card.addEventListener("animationend", ()=>card.classList.remove("dropped"), {once:true});
```

Reduced motion additions:
`.dropped { animation:none; } .card.dragging, … { transform:none; }`

## Repo conventions to follow

- Each view has its own drop wiring (board `:989`, matrix `:1132`, levels
  `:1190`, timeline pool `:1248`, list headings `:936`) — mirror the exact
  local variable names in each when adding the `.dropped` tag.
- `canAutoRefresh()` (`:1764`) checks `document.querySelector(".dragging")` —
  do not rename that class.

## Steps

1. Add the lift/ghost transitions for the four `.dragging` variants.
2. Add background/border transitions to the five drop-target element types
   (verify class names at each cited handler first).
3. Add the `.dropped` settle animation and tag the moved element in each of
   the five drop handlers.
4. Append reduced-motion overrides.

## Boundaries

- Do NOT attempt FLIP animations of sibling cards reflowing — native DnD +
  full re-render makes that a separate project.
- Do NOT change any drop semantics, dataTransfer payloads, or the classes JS
  keys on (`dragging`, `drop`).
- Do NOT add motion to the OS-rendered drag image (not possible; don't fake it
  with a custom drag layer — out of scope).

## Verification

- **Mechanical**: `uv run pytest -q` — all pass.
- **Feel check** (needs a board with a few projects):
  - Start dragging a board card: it dims+shrinks over ~120ms rather than
    blinking to 40%.
  - Sweep the pointer across three columns fast: highlights crossfade; no
    strobe.
  - Drop: the card lands with a barely-visible settle (1.02→1). At 10% speed
    in the Animations panel it reads clearly; at full speed it's felt, not
    seen.
  - Drag a task onto "Today" in the sidebar: same eased highlight on the
    nav item.
- **Done when**: a full drag-drop cycle contains zero hard visual cuts.
