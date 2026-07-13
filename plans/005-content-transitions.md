# 005 — Content transitions: list navigation, view switch, loading states

- **Status**: DONE
- **Commit**: 60d36f4 (+ uncommitted frontend extraction to `src/suur_things_mcp/static/index.html`)
- **Severity**: MEDIUM
- **Category**: Missed opportunities / Purpose & frequency
- **Estimated scope**: 1 file, ~15 lines CSS + ~5 lines JS

- **Depends on**: plan 000 (tokens)

## Problem

Selecting a list, switching List↔Matrix↔Cards↔Timeline, and the auto-refresh
re-render all replace `#content` wholesale — the new DOM pops in fully formed,
and a "loading…" placeholder flashes even for sub-100ms fetches:

```js
// src/suur_things_mcp/static/index.html:831-832 — current
const c=$("#content"); $("#filterbar").classList.remove("show"); c.innerHTML=`<div class="empty">loading…</div>`;
const data=await getJSON("/api/items?id="+encodeURIComponent(sel.id));
```

Navigation happens tens of times a day → the entrance must be a barely-there
opacity fade (~120ms), no movement, and it must NOT run on the silent 25s
auto-refresh (that would make the board pulse).

## Target

```css
/* content entrance — opacity only, fast */
#content.swap-in { animation: content-in var(--dur-fast) var(--ease-out); }
@keyframes content-in { from { opacity: 0; } }
/* loading placeholder: only becomes visible if the fetch is actually slow */
.empty.loading { opacity:0; animation: content-in 1ms 150ms var(--ease-out) forwards; }
```

```js
// in renderList (src/…/index.html:821), replace the placeholder line:
c.innerHTML=`<div class="empty loading">loading…</div>`;
// …after the data arrives and the view is rendered (end of renderList), trigger
// the entrance ONLY for user-driven renders:
c.classList.remove("swap-in"); void c.offsetWidth; c.classList.add("swap-in");
```

Auto-refresh exemption: `softRefresh()` (`:1779`) calls `loadSidebar(); route();`.
Give `renderList` an opt-out — simplest faithful-to-codebase approach: set a
module-global `SILENT=true` around the `route()` call in `softRefresh` and skip
the `swap-in` re-trigger when `SILENT` is set:

```js
let SILENT=false;
function softRefresh(){ …existing cursor gate…; SILENT=true; loadSidebar(); route(); setTimeout(()=>{ SILENT=false; …scroll restore… }, 280); }
// in renderList: if(!SILENT){ c.classList.remove("swap-in"); void c.offsetWidth; c.classList.add("swap-in"); }
```

Reduced motion: `#content.swap-in { animation: none; }` — but keep
`.empty.loading`'s delayed reveal (it's anti-flicker, not decoration).

## Repo conventions to follow

- Globals are UPPERCASE module-level `let`s (`MODE`, `CREATING`, `LAST_CURSOR`)
  — `SILENT` follows that pattern, declared next to them (~:490).
- The scroll-restore timing in `softRefresh` (280ms) is load-bearing — don't
  change it.

## Steps

1. Add the two CSS rules + keyframes.
2. Mark the loading placeholder with `.loading` in `renderList` (and in the
   board renderer `renderBoard` if it has the same placeholder — search for
   `loading…`).
3. Add the `SILENT` global and gate the `swap-in` retrigger.
4. Reduced-motion: append `#content.swap-in { animation:none; }`.

## Boundaries

- Do NOT add translate/scale to content entrances (frequency rule — opacity
  only).
- Do NOT animate the sidebar re-render.
- Do NOT touch the cursor-gating logic in `softRefresh` (it decides WHETHER to
  refresh; this plan only decides how it looks when it does).

## Verification

- **Mechanical**: `uv run pytest -q` — all pass (a source-guard test asserts
  `if(c0.cursor===LAST_CURSOR) return` still exists — do not break it).
- **Feel check**:
  - Click between Today/Anytime/a project: content fades in ~120ms; fast
    consecutive clicks never stack animations or flash "loading…".
  - Throttle network to Slow 3G (DevTools): "loading…" appears only after
    ~150ms, so fast loads never flicker.
  - Leave the dashboard open next to Things, add a task in Things, wait for
    the 25s poll: rows update WITHOUT any fade (silent refresh).
- **Done when**: navigation feels continuous, refresh is invisible, no
  loading flash on fast fetches.
