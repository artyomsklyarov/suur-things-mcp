# SUUR Things MCP — user actions

Updated: 2026-10-10. This is an owner checklist, not an engineering backlog. [PLAN.MD](PLAN.MD) contains implementation work; [STATUS.MD](STATUS.MD) distinguishes local, public and live acceptance. Checked items have evidence or an explicit decision; unchecked optional concepts are not obligations.

## Decisions and delegated work already done

- [x] Keep Things 3 as canonical task storage and use read-only SQLite plus official URL Scheme writes.
- [x] Keep dashboard planning metadata local and separate from canonical task fields.
- [x] Complete the authorized autonomous improvement run: 23 verified improvement iterations, nine dreams, three complete epics.
- [x] Preserve the ten pre-existing dirty files during that autonomous run; [historical hashes](.autoloop/artifacts/protected-final.json) confirm it.
- [x] Authorize the full intended checkout, including the existing staleness update, to be committed to the public GitHub repository (2026-10-10).
- [x] Authorize a new public version release (2026-10-10); 0.10.0 is the prepared, previously unpublished version.
- [x] Request separate detailed product/technical/status/user-action/unfinished-plan documents.
- [x] Enable the completed compact/keyboard-placement improvements by default; no flag setup is required.

## Current release — delegated to this session

No further approval is needed for the GitHub/PyPI release already requested. These are execution receipts, not requests for the user to repeat work.

- [x] Complete the five documents, README/changelog consistency and reviewed 0.10.0 checkpoint.
- [x] Pass the release fixture gate and inspect wheel/sdist metadata and packaged frontend.
- [ ] Commit/push the full intended checkout, pass protected-main CI and merge the release PR normally.
- [ ] Publish GitHub `v0.10.0` and verify the existing PyPI Trusted Publishing job.
- [ ] Verify fresh PyPI metadata, both distributions and package contents; record URLs/hashes in STATUS.

## Personal installation and live acceptance

- [ ] When ready to use the new public version, refresh the installed package and restart the MCP client/server. Use the install method you actually use: `uv tool upgrade suur-things-mcp` for a persistent tool, or `uvx --refresh --from suur-things-mcp==0.10.0 suur-things-mcp dashboard` for the pinned dashboard. Do not treat a package refresh as proof that an already running dashboard process restarted.
- [ ] Confirm the running dashboard/About version and connected MCP tools/prompts show 0.10.0, including `stale_review` and `stale_sweep`.
- [ ] Choose a disposable Things project/task for live acceptance; keep it separate from meaningful work. Record the original title/notes/tags/status/dates.
- [ ] Enable Things URLs if not already enabled and supply its modification token through your existing local secure setup. Never put it in these docs, the repository or a public bug report.
- [ ] Define the exact live test operations before execution: create, title/notes/scheduling/tag update, checklist append, complete/cancel and a small batch if desired. Verify actual fields and modification timestamps after each; retain records rather than deleting them as cleanup.
- [ ] Test Priority Levels using existing Things tags, checking that unrelated tags survive and unmapped/no-token actions are unavailable.
- [ ] Test one local image attachment with and without note-reference sync; distinguish saved bytes from whether Things received the file reference.
- [ ] Confirm any existing launchd dashboard restarts into the new package version without duplicate browser windows/port loops. Installing or changing a personal service is a separate local decision; this release does not perform it.

These steps have not been performed by the fixture suite. Publication is complete independently of personal live acceptance.

## Optional agent and repository integrations

- [ ] If using dashboard Organize/Triage/Calm, choose Claude or Codex and the model/account you want. Confirm your CLI login and understand its usage cost/privacy. Live model calls were not made during verification.
- [ ] Review a synthetic/disposable organizer proposal before applying to valuable tasks. Check the exact selected fields, appended notes, additive tags and destinations.
- [ ] If using repo launch buttons, choose an existing editor command and terminal app; link the correct local path(s), then verify editor/terminal/GitHub actions on your own machine.
- [ ] If using GitHub PR pulse, confirm your `gh` setup is usable for the selected repository; no GitHub credential is bundled by this server.
- [ ] Back up your personal config/attachment directory before manual repair or moving machines. Keep token backups private. Understand that `file://` references/local repo paths do not automatically become portable through Things Cloud.

## Product decisions for optional future work

Decide only if one of these directions is useful; no active implementation is waiting on them.

- [ ] Audit/undo: define retention/location/privacy and how to handle edits made after the recorded change. Choose whether a compensating Undo is worth the complexity; it cannot be advertised as a Things transaction.
- [ ] Local semantic search/ontology: choose permitted model size/license, optional dependency footprint and personal-data indexing boundaries before benchmarking.
- [ ] Personal-history search: define retention/export/encryption/deletion policy before collecting historical records.
- [ ] Agent comparison, energy-aware or quarter planning: choose a privacy-safe corpus, model/account, spending cap and review rubric before any live evaluation.
- [ ] Voice: decide on-device versus provider processing, privacy and accessible review behavior before microphone permission changes or recording.
- [ ] Private cross-device overlay sync: choose conflict/key-recovery/account/storage policy before a provider implementation. Team collaboration is not part of the present product plan.
- [ ] Manual accessibility acceptance: use your real keyboard/VoiceOver/browser zoom workflow and record concrete barriers if you want broader certification than the fixture suite.

## No outstanding approval for these historical items

- [x] Advanced keyboard placement (historical H11) was implemented as E03.
- [x] The requirement to leave the earlier ten dirty files uncommitted applied to the autoloop; the new full-checkout/release instruction supersedes that restriction for this release.
- [x] New project-timeline and warning-only time-budget ideas were evaluated and rejected for insufficient demonstrated value; they are not artificial approval blockers.

Engineering follow-ups such as staleness edge cases, the existing dependency warning and compatibility coverage belong in PLAN, not as setup tasks imposed on the user.
