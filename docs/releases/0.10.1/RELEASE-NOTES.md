# SUUR Things MCP 0.10.1

This patch explicitly emits core metadata 2.4 for wheel and sdist, fixing the existing publisher's rejection of metadata 2.5. The GitHub 0.10.0 checkpoint is preserved; its PyPI upload failed before transfer. No runtime dependency, Python floor, publishing configuration or credentials change.

Includes the complete 0.10.0 update, which adds reviewable stale-backlog cohorts and makes the local dashboard easier to use with a keyboard and in narrow windows, while hardening attachment/config storage and asynchronous navigation.

## Added

- `stale_review`: disjoint stale Inbox, never-touched, past-scheduled and loose-item queues, with configurable thresholds, full totals/capped samples, age histogram and project summaries.
- `stale_sweep`: optional, review-first workflow. Age does not imply task value; exact item lists require approval before bulk changes.
- Compact-card age/idle signals.
- Native keyboard destination controls for Matrix, Levels and boards, plus explicit timeline scheduling/change/unscheduling.
- Five detailed project handoff documents and a safe verification/recovery guide.

## Improved

- Full-width content and menu navigation in windows <=800px.
- Named dialogs, focus containment/return, keyboard navigation and clearer light/dark text/checkbox states.
- Byte-preserving corrupt-config recovery, fail-closed settings reads, atomic temporary files and concurrent attachment caps.
- Attachment path/symlink containment, API validation/error envelopes, supported preference preservation and organizer output scope checks.
- Stale responses no longer replace newer navigation. Optional Things note-sync failure does not hide successful image storage.

## Verification and compatibility

238 tests pass with zero skips in the complete local fixture gate; lint, compilation and wheel/sdist builds pass. Real Chromium tests use synthetic tasks and intercepted mutations. Python >=3.10 remains supported; things.py now requires >=1.0. One existing Starlette/httpx test-client deprecation remains.

Real Things mutation acceptance, live model quality and comprehensive manual accessibility/lifecycle checks remain separate. No tasks were modified by this verification. Canonical Things writes still use the official URL Scheme; planning data stays local. Diagnostic `?compact=0` / `?placement=0` fallbacks remain available.

## Update

```sh
uv tool upgrade suur-things-mcp
# Or refresh a uvx dashboard invocation:
uvx --refresh --from suur-things-mcp==0.10.1 suur-things-mcp dashboard
```

Restart an existing MCP/dashboard process to use the new package. See the README and STATUS.MD for details and acceptance boundaries.
