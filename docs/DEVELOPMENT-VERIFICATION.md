# Safe local verification and overlay recovery

SUUR Things MCP reads Things SQLite data and dispatches mutations through the official URL Scheme. The dashboard also owns a separate JSON overlay for boards, repo links, priority placement, preferences, attachments and time blocks. A green fixture suite proves local behavior; it does not prove that a real Things task accepted a write.

## Reproduce the full check

From the repository root, use an existing development environment with pytest, Ruff and Playwright/Chromium installed. The repository's existing development setup remains authoritative; this guide adds no dependencies or version requirements.

```sh
.venv/bin/python .autoloop/scripts/verify.py local-check
```

The harness runs Ruff, Python compilation, all pytest tests, and offline source/wheel builds. It creates a temporary synthetic Things database and config, disables the environment/token-file auth paths, and removes the temporary directory afterward. Things mutations and organizer processes are mocked by tests. No service is installed and no dashboard is opened against personal tasks. Loopback sockets and Chromium must be available; a restricted sandbox may require permission for those local resources.

Results are in `.autoloop/artifacts/local-check.txt`. The gate parses a temporary pytest JUnit report and rejects skipped tests, missing/malformed reports, empty execution, errors and failures before building. Expect zero skipped tests with this harness. A missing Chromium executable is an environment failure, not a passing browser check. Builds use the installed/cached toolchain (`uv build --offline`) and do not publish anything. The existing Starlette/TestClient deprecation is recorded separately from new warnings.

There is no configured standalone typechecker. `ruff format --check src tests` is an advisory audit: existing compact-style files and pre-existing work must not be reformatted en masse. Run Ruff formatting on new test files or the files you actually own.

## See the dashboard safely

```sh
.venv/bin/python .autoloop/scripts/capture.py local-screens
.venv/bin/python .autoloop/scripts/capture.py local-empty project
.venv/bin/python .autoloop/scripts/capture.py local-advanced advanced
.venv/bin/python .autoloop/scripts/capture.py local-placement placement
.venv/bin/python .autoloop/scripts/capture.py local-slots slots
```

Each command serves a disposable synthetic fixture at an ephemeral loopback port, captures desktop and 390px light/dark images, and stops its server. Normal captures include Preferences and Trash; `project` shows an empty standalone project; `advanced` shows Matrix and Timeline; `placement` shows Matrix, Levels and Board controls; `slots` seeds a local time block and shows its scheduling dialog. Read every PNG before judging the UI. `report.json` records page exceptions and relevant layout geometry.

The dashboard automatically uses compact navigation at widths up to 800px. `?compact=0` is a diagnostic fallback to the old fixed sidebar. Keyboard placement is default-enabled; `?placement=0` retains the prior controls for diagnosis. The browser interaction tests intercept every API request, so editing/completion/config actions in those tests never reach Things or user config.

## Handle unreadable or corrupt overlay files

`SUUR_THINGS_CONFIG` selects an overlay path; otherwise the application uses its normal local config path from `config._path()`. Do not change auth, service or production settings while diagnosing an overlay.

- Missing file: defaults are returned; no recovery copy is needed.
- Invalid JSON, invalid UTF-8 or a non-object JSON root: the original bytes remain in place and an exclusive sibling `board.json.corrupt-<sha256-of-original-bytes>` is preserved before defaults are returned. A later explicit successful save may replace the active file; the recovery copy remains.
- A different corrupt payload gets its own digest-named copy. Repeated reads reuse the matching copy instead of replacing it or generating an unlimited sequence.
- Other I/O errors fail closed. Load/merge must not overwrite a file that could not be read. The dashboard displays a settings error and prevents overlay writes until a successful retry.

For manual recovery, close dashboard writers first, copy the active file and all recovery siblings to a separate local review directory without deleting originals, and inspect the relevant copy. Repair a **new** JSON file with an object root; preserve unknown user records for review rather than guessing their meaning. Point a disposable `SUUR_THINGS_CONFIG` at that repaired file and validate with the existing config functions before choosing to replace a personal active file. Never paste task data, tokens or private paths into public artifacts. Automated checks should use only synthetic fixtures.

Attachments are stored outside Things in the overlay's attachment directory. Only recorded image metadata resolves to a contained file path. Unsafe identifiers, symlink escapes and paths outside the resolved root are rejected; failed detach preserves both bytes and metadata. Do not delete recovery copies or attachment directories to fix an error. Upload caps are enforced while holding the existing cross-process lock. After a successful store, adding a Things note reference is best-effort: the upload remains successful and `note_updated` is false if that separate sync fails. This does not mean the image or metadata failed to save.

## Keep acceptance evidence separate

Unit/API/browser tests, fixture screenshots and package builds are local evidence. A real create/update/complete acceptance check requires a user-owned disposable Things task and an explicit live-write decision. Organizer tests validate submitted-ID boundaries and malformed proposals with mocked processes; they do not verify paid models, CLI credentials or live proposal quality. Release/deployment/service changes are separate work.
