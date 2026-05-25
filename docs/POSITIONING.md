# Positioning & story

Source material for the website / launch copy. Not user docs — this is the *why*.

## The one-liner

**Things-level calm, plus the few modern affordances it's missing — open, fast-moving, and shaped by the people who use it.**

## The insight

People who love Things 3 don't want a feature-bloated Todoist clone. They keep coming back to Things for the same reasons: calm design, low friction, no subscription, native Apple feel. (See r/thingsapp — the recurring theme is "I tried X, I came back.")

But the same threads name the gaps that make people occasionally stray:

- No natural-language capture
- No web / Windows access
- No collaboration / shared lists
- Awkward attachments & context links
- Limited recurring-task control
- No calendar / time-blocking view
- Little customization (overwhelm for ADHD / high-volume users)
- Slow, opaque product evolution

The opportunity is **not** to out-feature Todoist. It's: *Things-level calm + 3-5 missing modern affordances, layered on safely, without betraying what people love.*

## Why we can do this safely

SUUR Things MCP doesn't replace Things or fork its data. It **reads** the local Things database (read-only) and **writes only through Cultured Code's official URL Scheme** — the exact automation path they endorse. It physically can't corrupt your database. Anything Things doesn't model (boards, priority, repo links, attachments) lives in a local overlay keyed by Things' own task IDs, never written back.

So we add capability *on top* of the app you already trust, instead of asking you to switch.

## What we add (and what we won't)

**We build (Things-calm affordances):**

- **Your AI agent can run your Things** — capture, triage, plan, review, all in plain language. The NLP people want from Todoist, you already have: just talk to your agent.
- **A local dashboard** with the views Things lacks — an Eisenhower Priority Matrix on any list, a day **timeline / time-blocking** view, a card view, focus/declutter modes for overwhelm.
- **Calm-Today triage** — the agent turns a 30-item pile into one next action plus a realistic short list, and defers the rest. No guilt.
- **Repo-aware project boards** for people who build software.

**We won't** (these would betray the audience): become busy, AI-heavy, subscription-first, or team-workflow-first. Web/Windows and real collaboration need a cloud backend Things has no API for — that's a different product with a different model, a deliberate choice, not a drift.

## The "why us" angle (addresses the "what are they working on?" anxiety)

Things ships slowly and quietly, by design. SUUR Things MCP is the opposite by design: **open source, fast-moving, and community-shaped.** Anyone can propose what gets built next and vote on it. We're the modern layer for people who love the calm but want a say in the pace.

## Tone

Calm, confident, a little opinionated. Not hypey, not corporate, not "AI-powered everything." We respect Things and its users; we're additive, not competitive.
