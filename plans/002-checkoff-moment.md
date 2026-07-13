# 002 — The checkoff moment: instant fill, small pop, calm matrix exit

- **Status**: DONE
- **Commit**: 60d36f4 (+ uncommitted frontend extraction to `src/suur_things_mcp/static/index.html`)
- **Severity**: HIGH
- **Category**: Missed opportunities (signature interaction)
- **Estimated scope**: 1 file, ~15 lines CSS + ~6 lines JS
- **Depends on**: plan 000 (tokens)

## Problem

Completing a task is the emotional core of a to-do app — Things 3 fills the
checkbox with a satisfying micro-pop. Here the checkbox snaps to filled with no
transition, and worse, feedback waits for the server round-trip:

```js
// src/suur_things_mcp/static/index.html:962-963 — current (list rows)
if(!done&&!cancel){ const box=row.querySelector(".box"); box.title="Complete"; box.style.cursor="pointer";
  box.onclick=(e)=>{ e.stopPropagation(); applyStatus(it.uuid,"completed").then(ok=>{ if(ok) rerenderCurrent(); }); }; }
```

```css
/* src/suur_things_mcp/static/index.html:104-108 — current */
.box { width:17px; height:17px; flex:0 0 17px; border:1.5px solid var(--check-border);
  border-radius:5px; display:flex; align-items:center; justify-content:center; }
.box.done { background:var(--accent); border-color:var(--accent); }
.box.done::after { content:"✓"; color:#fff; font-size:11px; font-weight:700; }
```

In the Matrix view the completed card is removed with `el.remove()`
(`:1127-1128`) — it vanishes with no exit at all.

## Target

CSS — the box fills fast and the check pops from 0.6 (never 0):

```css
.box { /* keep existing properties, add: */
  transition: background var(--dur-fast) var(--ease-out), border-color var(--dur-fast) var(--ease-out); }
.box::after { transform: scale(0.6); opacity: 0;
  transition: transform 160ms var(--ease-out), opacity 120ms var(--ease-out); }
.box.done::after, .box.cancel::after { transform: scale(1); opacity: 1; }
```

NOTE: `::after` only renders when `content` is set; move `content:"✓"` /
`content:"✕"` handling so the base `.box::after` has `content:""` and the
done/cancel variants only change color/char — concretely:

```css
.box::after { content:"✓"; color:transparent; transform:scale(0.6); opacity:0;
  font-size:11px; font-weight:700;
  transition: transform 160ms var(--ease-out), opacity 120ms var(--ease-out); }
.box.done::after { color:#fff; transform:scale(1); opacity:1; }
.box.cancel::after { content:"✕"; color:#fff; font-size:10px; transform:scale(1); opacity:1; }
```

JS — optimistic feedback: fill the box the moment it's clicked, before the
URL-scheme write resolves (the write-verified server call still decides whether
the re-render keeps it):

```js
box.onclick=(e)=>{ e.stopPropagation(); box.classList.add("done");
  applyStatus(it.uuid,"completed").then(ok=>{ if(ok) rerenderCurrent(); else box.classList.remove("done"); }); };
```

Matrix exit (`:1127-1128`): fade + shrink before removal:

```js
b.onclick=(e)=>{ e.stopPropagation(); b.classList.add("done");
  applyStatus(t.uuid,"completed").then(ok=>{ if(ok){
    el.style.transition="opacity 200ms var(--ease-out), transform 200ms var(--ease-out)";
    el.style.opacity="0"; el.style.transform="scale(0.96)";
    setTimeout(()=>el.remove(), 200);
  } else b.classList.remove("done"); }); };
```

Reduced motion (append to the plan-000 block): `.box::after { transition:none; }`
— the fill color change stays (state feedback), the pop goes.

## Repo conventions to follow

- JS binds handlers programmatically right after building elements (CSP:
  no inline handlers) — e.g. `rowEl` at `:954`. Keep that pattern.
- The edit-card checkbox `#ec-box` (`.ec-box`, styles at `:198-201`) completes
  via `completeTask()`; give it the same box/::after treatment (its class names
  are `ec-box`/`done`).

## Steps

1. Update the `.box` CSS block (and `.ec-box` equivalents) per Target.
2. Make the list-row `box.onclick` optimistic (rowEl, `:962-963`).
3. Make the matrix checkbox exit fade+shrink (`:1127-1128`).
4. Append the reduced-motion selector.

## Boundaries

- Do NOT change `applyStatus` or any server code.
- Do NOT make completed rows disappear from lists — the deliberate product
  behavior is that they linger checked-off until they log (documented in the
  README); only the Matrix removes cards, because placement is the view.
- If the cited code has drifted, STOP and report.

## Verification

- **Mechanical**: `uv run pytest -q` — all pass.
- **Feel check** (fresh foreground dashboard; needs `THINGS_AUTH_TOKEN` to
  actually complete — use a throwaway task):
  - Click a checkbox: it fills the same frame you click; the ✓ pops in small→
    full over ~160ms. No wait on the network.
  - In Matrix view, complete a card: it shrinks-fades out over ~200ms, no jump
    when siblings reflow.
  - Slow to 10% in the Animations panel: the ✓ never starts from nothing
    (scale 0.6, not 0).
  - Reduced motion: box still fills (color), no pop, matrix card just fades.
- **Done when**: checkoff feels instant and warm, and a failed write visibly
  reverts the box.
