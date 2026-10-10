# Decisions

2026-10-10: preserve all ten pre-existing dirty files byte-for-byte, including manifests/lock. Use already installed dependencies and offline builds. No version bump. Synthetic DB/temp config/token paths for all verification and screenshots; never invoke metered organizer CLIs or real URL Scheme writes. Keep app architecture and motion intent. Format audit advisory because baseline has 11 compact-style files and user work must not be reformatted.

Log hashes are filled on the next iteration from committed git history; the final entry identifies itself by its unique commit subject to avoid a self-referential hash. Each product iteration includes state and evidence in one commit.

## NEEDS HUMAN DECISION

- H01: Pre-existing staleness-review work in ten dirty files (artifacts/preexisting-work.json). Review/test/commit it separately; loop will not stage it.
- H02: Real Things mutation acceptance: with a user-owned disposable Things task and token, verify create/update/complete and modified timestamps; delete nothing. No real writes authorized in this loop.
- H03: Environment Starlette 1.3.1 warns TestClient/httpx is deprecated. The manifest/lock are dirty and protected; a separate dependency review can choose a compatible test client or pins. Do not add httpx2 speculatively.
- H04: Publishing or deploying these local commits is excluded. Review branch diff, then use the normal release process if desired.

- H05: Audit trail proposal: persist an append-only local review record with task UUID, proposed fields, user selection, URL dispatch and verified outcome; decide retention and privacy before specifying a migration.
- H06: Project timeline proposal: dev-only prototype joining linked project tasks and local git timestamps, without gh/network; decide whether this is the product's next direction before adding a view.
- H07: Semantic search proposal: benchmark a local model against fixture title/note search; approve model size, licensing and optional dependency before implementation.

Iteration 1: Path.relative_to on resolved paths replaces unsafe string-prefix checks. Detach rejects escaped paths and preserves metadata. B08 rejected after proper settled evidence; do not mistake transient screenshots for final theme behavior.

Iteration 2: use standard-library SHA-256 content-addressed recovery copies, exclusive creation and byte readback. Preserve original bytes until a successful explicit save. Read errors other than missing file propagate so load-modify-save cannot overwrite unread data. No dependency added.

Iteration 3: hold the existing cross-process lock from attachment-cap check through metadata save. Use standard-library NamedTemporaryFile for exclusive sibling temp creation; same-process parallel direct saves must not share a PID-only pathname. No extra dependency.

Iteration 4: model output must remain within submitted task IDs, with first suggestion per ID winning. Malformed scalar tags are ignored; a bare string is one tag, not characters. Code fences inside JSON notes are preserved. Model execution is mocked in regressions; no CLI auth, accounts or metered calls used.

Iteration 6: browser storage is cosmetic and failure must not stop startup. Keep last good/default CONFIG and display Retry on load failure; block config/link POSTs until settings are loaded so defaults cannot overwrite unknown state. Render sidebar errors within side-nav to preserve the footer and retry structure.

Iteration 7: E01 beats narrow-layout runner-up 20 vs 18 on user value/fit/feasibility/self-containment. Modal corrections are complete per slice, no incomplete new feature requires a flag. Preserve edit autosave and instant palette motion.

- H08: Time-budget proposal: dev-only timeline summary of configured minutes vs available day span, with no guessed estimates; decide whether users want warnings before introducing them.
- H09: Attention-map proposal: local synthetic proof of joining staleness and repo timestamps; decide retention/privacy and meaning of scores before surfacing real data.
- H10: Personal ontology proposal: optional local-only classification prototype; approve model/dependency/storage/migration scope before any training or indexing.
- H11: Advanced drag-view keyboard placement: specify an accessible per-card destination selector for board stages, quadrants and timeline blocks; decide preferred interaction before a larger view-controls epic. Existing task edit/complete remains keyboard accessible.

Dream 3 correction: H11 interaction design does not require human setup or sensitive permission. Reclassified as B17, a feasible Medium epic candidate, with a per-card destination selector as its concrete plan.
- H12: Return onboarding research: ask real users what they need after a break; only then prototype a dismissible local hint. No guesses about overdue-task guilt.
- H13: Energy-aware agent plan: user provides constraints; opt-in existing review workflow proposes a schedule; user reviews before URL Scheme updates. Any live model call needs separate authorization for metered work.
- H14: Decade-memory plan: synthetic local demo first; define retention/export/deletion and privacy guarantees before indexing personal history or choosing infrastructure.

Iteration 11: E02 is complete and default-enabled after all-view width tests and rendered inspection. Keep ?compact=0 as a reversible diagnostic fallback. No dependencies or platform changes.

Iteration 12: computed foreground/effective background colors, standard sRGB luminance; normal text target 4.5:1 from https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html . Shared theme-specific muted/priority/on-accent tokens preserve semantic hues. No dependencies. Existing resize regression now waits for BOTH sidebar/main inert states because sidebar is already non-inert while its menu is open; assertions unchanged.

Iteration 13: retain existing 200/ok=false read/storage error convention, use established 400 for malformed JSON/section/list types. Empty repository list still intentionally clears links, while wrong types preserve them. No dependencies.

- H15: Undo reviewed agent changes: first specify a local append-only before/after record with outcome verification; use a disposable task to prove a compensating URL Scheme update cannot overwrite intervening edits. Define retention and conflict handling before migrating config or offering Undo; never imply transactional Things writes.

Iteration 14: B15 selected before B11 because equal Medium impact has lower risk and effort. Preserve only the two existing organizer integrations, and arbitrary nonempty model string without inventing a model catalog. Preferences UI carries forward other existing preference keys; no model execution or account configuration.

Iteration 15: a monotonic generation counter is enough; cancellation would add complexity without benefit for cheap read-only local requests. Guard every view after await and before both error/success rendering and global list state. No new dependency.

- H16: Quarter planner: specify input goals and review boundaries using synthetic projects first. Any real model execution or organization-specific decision needs opt-in authorization; do not dispatch unreviewed updates. Feasible local prerequisites already exist, but live metered planning is outside this run.

- H17: Live organizer comparison: choose approved models, a capped monetary budget, privacy-approved task fixtures and a rubric; run identical mocked fixtures first. This loop makes no metered calls or credential changes.
