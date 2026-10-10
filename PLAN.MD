# SUUR Things MCP — unfinished work and future plans

Updated: 2026-10-10. This document records work not implemented or not accepted. It does not restart the completed autoloop or promise every dream idea. Product intent is in [CONTEXT.MD](CONTEXT.MD); implementation contracts in [SPEC.MD](SPEC.MD); current evidence in [STATUS.MD](STATUS.MD); owner choices in [TODO.MD](TODO.MD).

## Current release completion

0.10.0 combines the existing staleness feature with 23 committed autoloop improvement slices. The user has authorized both the full checkout commit and public release. No version/account/permission question remains for the existing GitHub → PyPI release workflow.

Release progress:

- Done: all five docs, changelog/README consistency, full no-skip gate and package inspection, public source update, protected-main CI and normal merge through PR #53.
- Done: GitHub v0.10.0 release at the checked merge commit.
- Failed: its PyPI action rejects Hatchling's metadata 2.5 before upload. The public tag/release is retained; this does not count as PyPI publication.
- Done: 0.10.1 metadata 2.4 patch, repeated full no-skip gate and package inspection, required PR CI, normal merge, GitHub/PyPI publication and downloaded public registry/file/hash checks.
- Done: STATUS/TODO and the release verification record contain the observed patch outcomes and machine-readable receipts; these updates form the final documentation checkpoint.

Release acceptance reached: five detailed handoff documents, full source update merged to main, GitHub release public, release job successful and 0.10.1 public files verified on PyPI, with an isolated downloaded-wheel install/import smoke check. This is separate from live task acceptance. No tag rewriting, publishing secrets/config changes or real task mutations are needed.

## P1 — Live Things acceptance protocol

**Status:** Not performed. **Priority:** First acceptance step after publishing. **Dependency:** User-owned disposable records/token and agreed operation scope; no automatic private task writes.

Build a bounded test matrix over real macOS/Things: read-only discovery; create a task/project; resolve created UUID; update title/notes/when/deadline/tags; append checklist; complete/cancel; mapped-level update; small JSON batch; image note reference. Record original and expected fields, returned dispatch/stamp indicators, actual read-back and any delays.

Pay special attention to unknown tags, unknown UUIDs, duplicate create titles, absent write token, Things not running, asynchronous modification stamps and partial batches. Distinguish `ok`, `applied`, verified fields and unknown outcomes. No automatic repeat of a dispatched operation if acceptance is uncertain, and no delete-based cleanup.

Acceptance: exact field observations, stable identity, no unrelated task changes, token redacted in logs, and clear unverified outcomes. This validates existing functionality, not a new feature. A fixture test is insufficient to mark it done.

## P2 — Staleness correctness hardening

**Status:** Main feature implemented; extra cases not covered. **Impact/risk/effort:** Medium / Low–Medium / Small independent slices. **No new account/dependency required.**

### Missing and future timestamps

Create opt-in rows with null/malformed/future creation/modification timestamps. Define how histogram “unknown” counts relate to `open_todos` and whether negative age/idle values are clamped. Keep no-data distinct from zero age; maintain full cohort totals when display lists are capped.

Acceptance: all open records are accounted for without assigning age-based certainty to unknown data; no crash on supported malformed inputs; deterministic boundary tests at 30/90/180/365 days.

### Stable project identity

Current `clusters` uses project title as its grouping key. Add a fixture with different UUIDs sharing a title. Prefer UUID-keyed aggregation with title as display data; add project UUID to summaries in a backward-compatible response extension. Never let a merged title summary become an implicitly approved bulk UUID list.

Acceptance: same-title projects remain distinct, counts/oldest-idle are correct, disjoint cohort invariants remain and existing consumers still work.

### Projects with headings and no open tasks

Current dead-project SQL checks any open child, not specifically type-0 to-dos. Add heading-only and completed-child fixtures, then constrain the emptiness test to the intended open to-do kind. Align its naming/meaning with `overview`'s “no next action” output.

Acceptance: a heading is not an open task; projects with actual open work are excluded; completed/canceled/trashed children do not produce false activity.

### Snapshot freshness and scale

Use only synthetic WAL/database files to test read-only aggregation freshness while writes occur through fixture setup, not production SQLite. Compare current immutable snapshot behavior with explicit read-only snapshot choices before changing it. Benchmark realistic synthetic backlog sizes and record before/after time/memory only if performance changes are justified.

Acceptance: no production database write path, no data duplication, no lock regression, factual measured scale limits and no unmeasured “faster” claims.

These follow-ups need not become one large epic. Protect each area first, implement one behavior correction, then run the complete gate.

## P3 — Dependency warning and compatibility review

**Status:** One Starlette/TestClient/httpx deprecation remains; suite passes. Existing Dependabot PRs are proposals, not adopted upgrades.

Inspect compatibility of MCP, Starlette and the supported test client before changing pins/dependencies. Select a supported migration only when the actual stack works across Python >=3.10 and the Linux fixture/macOS live boundaries. Do not silence warnings or weaken tests. Update manifest and lock together, document any new dependency rationale, and keep minimum language/platform floors unless separately decided.

Acceptance: zero new warnings, old deprecation resolved by a supported setup, all 238+ strict tests run without skips locally, Linux CI passes and distribution dependency metadata matches intended floors. MCP major-version proposals require explicit API/transport compatibility investigation rather than a routine bump. Existing GitHub setup-uv emits a Node 20 migration warning; action-runtime maintenance needs a separate reviewed workflow change, not a publishing credential change.

## P4 — Broader manual accessibility acceptance

**Status:** Core/advanced keyboard implementations complete; comprehensive manual audit not performed. **Dependencies:** Real macOS VoiceOver/browser/zoom workflow and recorded observations.

Inspect screen-reader names and reading order for sidebar/areas/palette; repeated keyboard navigation through task lists and stacked dialogs; focus after errors/save/navigation; native time/select controls; compact menu and horizontal board scrolling. Add 200%/400% zoom, long titles, many tags/attachments, large item pools and touch targets to the evidence set. Test both themes and reduced-motion preferences.

Acceptance: observed barriers are filed precisely with steps and before evidence; fixes retain autosave/navigation/data/actions; no blanket conformance claim from sampled ratios alone. Do not rewrite the entire frontend to satisfy a cosmetic preference.

## P5 — Desktop lifecycle and installed upgrade acceptance

**Status:** Lifecycle commands implemented/unit-tested; actual installed service/browser upgrade not verified in this run.

Use a disposable config/fixture-backed dashboard first. Check app-mode fallback when no supported Chromium app exists, foreign-process port handling, compatible-instance reuse, no-open service behavior and version-triggered reload. On the user's existing service only with explicit local scope, record command/package resolution and restart behavior.

Acceptance: no duplicate instances/windows or port loops, correct installed version, preserved config/attachments and a reproducible upgrade path. Do not install/change LaunchAgents as an incidental docs test.

## Optional roadmap candidates — no active epic

None of the following has been started as a committed product feature. Before promoting one, score user value/product fit/feasibility/self-containment and choose only one epic. Prefer synthetic, dev-only experiments and remove failed experiments without removing existing features.

| Candidate | Preparation and implementation sequence | Required decision / acceptance |
|---|---|---|
| Review audit trail | Define record/retention, append-only local before/proposed/selected/dispatch/observed outcomes, migration and fixture tests, then optional UI | Privacy/retention/location; no implicit personal history collection |
| Compensating Undo | First protect audit records; prove intervening-edit detection on disposable tasks; offer a compensating URL update only when safe | Conflict policy and live acceptance; never describe it as transaction rollback |
| Local semantic search | Benchmark existing text search on a fixture corpus; choose permitted model/license/size and optional dependency; dev-only local index | Measured usefulness and personal-data indexing policy; no automatic paid embedding calls |
| Personal ontology/history | Specify fields, storage/indexing/encryption/export/retention; synthetic demo, migration and opt-in collection | Explicit privacy/model/storage decisions; no guess at which history to retain |
| Energy-aware/quarter planning | User constraints and rubric; mocked proposals; existing per-field review path; live evaluation only under approved budget | Evidence of scheduling usefulness, model/account and monetary cap |
| Organizer model comparison | Identical privacy-safe corpus, scoring rubric and mocked baseline, then capped live runs | Provider/auth/privacy/spend decision; no automatic metered evaluation |
| Voice | Text-driven accessible review prototype first; choose processing/local/provider; permissions/privacy plan before audio | Microphone permission and recording approval; optional provider cost |
| Private overlay sync | Synthetic conflict/key-recovery specification; choose backend/account/encryption, migration, opt-in provider | New infrastructure and retention policy; local file references are not automatically portable |
| Return-after-absence help | User research, then small dismissible hint only if evidence warrants it | Actual user needs; no guessed guilt, fake urgency or forced queue-emptying |

## Completed or rejected work that must not be reopened automatically

- E01/E02/E03 are complete and enabled. Do not continue a preview milestone based on old epic text.
- Attachment containment/recovery/concurrency, startup settings guards, stale view reads, organizer scope checks, preference retention and no-skip gate are done with regressions.
- New project timeline and warning-only time-budget features were rejected for insufficient value; no user approval is pending for them.
- Replacing Things, direct database writes, a team planning platform and automatic task classification/mutations are outside current product fit.
- Animation/gamification or forced motivational urgency does not improve the stated calm product intent.

## Execution rules for the next engineering session

Read the five root docs, current Git status and actual source before acting. Preserve unrelated user work. Use the complete fixture gate, protect untested logic before refactoring, capture/read affected UI states, and keep acceptance layers distinct. New dependencies need written justification; credentials/config stay out of commits. Larger work gets a spec and complete small milestones, with a flag until usable. Release/real-task/model permissions are specific actions, not blanket authority for optional roadmap expansion.
