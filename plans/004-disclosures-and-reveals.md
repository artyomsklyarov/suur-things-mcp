# 004 — Disclosures: sidebar area collapse, edit-card editors, filter bar

- **Status**: DONE
- **Commit**: 60d36f4 (+ uncommitted frontend extraction to `src/suur_things_mcp/static/index.html`)
- **Severity**: MEDIUM
- **Category**: Missed opportunities / Interruptibility
- **Estimated scope**: 1 file, ~25 lines CSS + ~10 lines JS
- **Depends on**: plan 000 (tokens)

## Problem

Three disclosure surfaces teleport:

1. **Sidebar area collapse** — the chevron swaps glyphs (`▶`/`▼`) and
   `renderSidebar()` rebuilds the whole tree; projects appear/vanish with no
   motion:

```js
// src/suur_things_mcp/static/index.html:775-777, 793-794 — current
const collapsible=!!a.uuid, collapsed=collapsible&&COLLAPSED.has(a.uuid);
head.innerHTML=`<span class="chev">${collapsible?(collapsed?"▶":"▼"):""}</span>…`;
function toggleArea(uuid){ COLLAPSED.has(uuid)?COLLAPSED.delete(uuid):COLLAPSED.add(uuid);
  localStorage.setItem("collapsed-areas", JSON.stringify([...COLLAPSED])); renderSidebar(); }
```

2. **Edit-card editors** (When / Deadline / Tags rows) pop via a display
   toggle: `.ec-editor { display:none } .ec-editor.show { display:block }`
   (`:230-231`).

3. **Filter bar** appears via `.filterbar.show { display:flex }` (`:123-124`).

## Target

1. Chevron: one glyph, rotated — always render `▶` and rotate it 90° when
   open. Rotation transitions; a rebuilt DOM node lands in its final state
   (no animation on rebuild — correct, since the user only sees the click):

```css
.area-head .chev { transition: transform var(--dur-med) var(--ease-in-out); }
.area-head .chev.open { transform: rotate(90deg); }
```

```js
// in renderSidebar(), replace the glyph ternary:
head.innerHTML=`<span class="chev${collapsed?"":" open"}">${collapsible?"▶":""}</span>…`
```

   In `toggleArea`, toggle the class on the clicked chevron BEFORE calling
   `renderSidebar()` so the rotation is visible (the rebuild then replaces the
   node in-place at its final angle):

```js
function toggleArea(uuid, chev){ COLLAPSED.has(uuid)?COLLAPSED.delete(uuid):COLLAPSED.add(uuid);
  localStorage.setItem("collapsed-areas", JSON.stringify([...COLLAPSED]));
  if(chev){ chev.classList.toggle("open"); setTimeout(renderSidebar, 200); }
  else renderSidebar(); }
```

   (Pass the chevron element from the existing onclick at `:779`.)

2. Edit-card editors — grid-rows expansion (animatable, interruptible, no
   fixed heights):

```css
.ec-editor { display:grid; grid-template-rows:0fr; opacity:0; overflow:hidden;
  transition: grid-template-rows var(--dur-med) var(--ease-out), opacity var(--dur-med) var(--ease-out); }
.ec-editor > * { min-height:0; }
.ec-editor.show { grid-template-rows:1fr; opacity:1; }
```

   NOTE: `.ec-editor` children must sit in ONE wrapper for `0fr` to collapse
   them. `#ed-when` has two children (`#when-chips`, `#f-when`) — wrap the
   editor contents in a single `<div>` per editor (markup change allowed here).

3. Filter bar — fade+rise, keep the display toggle but add entrance:

```css
.filterbar.show { display:flex; animation: bar-in var(--dur-fast) var(--ease-out); }
@keyframes bar-in { from { opacity:0; transform:translateY(-3px); } }
```

   (Keyframes are acceptable: the bar isn't rapidly re-triggered.)

Reduced motion additions: `.chev { transition:none; } .ec-editor { transition:opacity var(--dur-fast) ease; } .filterbar.show { animation:none; }`

## Repo conventions to follow

- `.show` classes drive visibility everywhere — keep them; change what they do.
- JS binds after building nodes (CSP — no inline handlers); the chevron
  handler lives at `:779`:
  `head.querySelector(".chev").onclick=(e)=>{e.stopPropagation(); toggleArea(a.uuid);};`

## Steps

1. CSS: chevron rotation rules; delete nothing else.
2. JS: single-glyph chevron + class toggle + deferred re-render (Target 1).
3. HTML+CSS: wrap each `.ec-editor`'s children in one div; add the grid-rows
   transition (Target 2).
4. CSS: filter-bar entrance (Target 3).
5. Append the reduced-motion selectors to the plan-000 block.

## Boundaries

- Do NOT animate the sidebar project list's height itself (the tree rebuild
  makes a true expand/collapse a FLIP project — out of scope; the rotating
  chevron plus the 200ms beat carries the disclosure).
- Do NOT touch `#cmdk`, overlays, or drag code.
- If `renderSidebar`/`toggleArea` have drifted, STOP and report.

## Verification

- **Mechanical**: `uv run pytest -q` — all pass, including the browser test
  that opens the quick-add card (editors wrapped ≠ broken `autoGrow`).
- **Feel check**:
  - Click an area chevron: it rotates smoothly 90°; spam-clicking retargets
    mid-rotation (transition, never a restart).
  - In the edit card, tap 📅: the When row grows open in ~200ms; tapping 🏷
    while it's still opening feels fluid, nothing jumps.
  - Filter chips appear with a tiny rise when entering a tagged list.
- **Done when**: all three disclosures move instead of teleporting, spam-safe.
