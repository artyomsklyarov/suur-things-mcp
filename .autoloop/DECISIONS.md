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
