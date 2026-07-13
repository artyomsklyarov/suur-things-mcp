# 000 — Motion foundation: tokens, reduced-motion gate, animatable overlays

- **Status**: DONE
- **Commit**: 60d36f4 (+ uncommitted frontend extraction to `src/suur_things_mcp/static/index.html`)
- **Severity**: HIGH
- **Category**: Cohesion & tokens (enabler for every other plan)
- **Estimated scope**: 1 file (`src/suur_things_mcp/static/index.html`), ~30 lines of CSS

## Problem

The dashboard has **zero motion anywhere** — no `transition`, no `@keyframes`, no
easing exists in the file. Every state change teleports. Worse, the overlay
pattern makes motion impossible to add: overlays toggle `display:none → flex`,
which cannot transition.

```css
/* src/suur_things_mcp/static/index.html:311-312 — current */
.overlay { position:fixed; inset:0; background:var(--overlay); display:none; align-items:flex-start; justify-content:center; z-index:20; padding:60px 16px; }
.overlay.show { display:flex; }
```

There are also no easing/duration tokens and no `prefers-reduced-motion`
handling. Every later plan needs these three things in place.

## Target

1. Motion tokens in the existing `:root` block (which starts at
   `src/suur_things_mcp/static/index.html:9`, where the color variables live):

```css
/* add inside :root { … } */
--ease-out: cubic-bezier(0.23, 1, 0.32, 1);      /* entrances/exits — strong ease-out */
--ease-in-out: cubic-bezier(0.77, 0, 0.175, 1);  /* on-screen movement */
--dur-fast: 120ms;    /* hover, press, small feedback */
--dur-med: 200ms;     /* overlays, disclosures, content */
```

2. Overlays become animatable without changing any JS (the `.show` class and
   the `document.querySelector(".overlay.show")` checks keep working):

```css
/* target — replaces the two rules at :311-312 */
.overlay { position:fixed; inset:0; background:var(--overlay); display:flex; align-items:flex-start; justify-content:center; z-index:20; padding:60px 16px;
  visibility:hidden; opacity:0;
  transition: opacity var(--dur-med) var(--ease-out), visibility 0s linear var(--dur-med); }
.overlay.show { visibility:visible; opacity:1;
  transition: opacity var(--dur-med) var(--ease-out); }
```

   `visibility:hidden` (not `display:none`) keeps the element out of hit-testing
   and the a11y tree while allowing the opacity fade; the delayed `visibility`
   flip on close means the fade-out is visible.

3. A reduced-motion block at the END of the `<style>` section. Movement is
   dropped; opacity feedback stays (reduced motion ≠ zero feedback):

```css
@media (prefers-reduced-motion: reduce) {
  /* Later plans add their transform-animated selectors here. */
  .overlay, .overlay.show { transition: opacity var(--dur-fast) ease; }
}
```

## Repo conventions to follow

- All CSS lives in the single `<style nonce="__CSP_NONCE__">` block at the top
  of `src/suur_things_mcp/static/index.html` (lines 8–332). Add tokens to the
  existing `:root` and new rules near the code they affect.
- Variables are kebab-case with short names (`--row-hover`, `--card-bg`) —
  match that style.

## Steps

1. In `src/suur_things_mcp/static/index.html`, add the four motion tokens
   inside the first `:root { … }` block (light theme, line ~9). Tokens are
   theme-independent — do NOT duplicate them into the `.dark` block.
2. Replace the `.overlay` / `.overlay.show` rules (lines 311–312) with the
   target CSS above.
3. Add the `@media (prefers-reduced-motion: reduce)` block as the last rule
   inside `<style>`, with a comment saying later plans append selectors here.
4. Run the mechanical verification below.

## Boundaries

- Do NOT touch any JavaScript.
- Do NOT touch `#cmdk` specially yet (plan 001 handles the command-palette
  exemption).
- Do NOT add motion to anything else — this plan is only tokens + the overlay
  display→visibility conversion + the reduced-motion scaffold.
- If the cited lines don't match (drift), STOP and report.

## Verification

- **Mechanical**: `uv run pytest tests/test_dashboard.py tests/test_dashboard_browser.py -q`
  — all pass (the browser tests open real overlays; `openCreate('todo')` must
  still show the card and `#f-title` must be focusable/visible).
- **Feel check**: `uv run suur-things-mcp dashboard` on a random port
  (`SUUR: use a fresh foreground run, NOT the :8765 service`), then:
  - Click ＋: the dim backdrop fades in over ~200ms instead of popping.
  - Press Escape: it fades out; nothing is clickable behind it mid-fade.
  - With nothing open, click through the page — no dead zone (the always-flex
    overlay must not intercept clicks when hidden).
  - DevTools → Rendering → emulate `prefers-reduced-motion`: the fade is
    near-instant but still an opacity change.
- **Done when**: overlays fade instead of popping, all tests pass, and the
  tokens exist for later plans.
