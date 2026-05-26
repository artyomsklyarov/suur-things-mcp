# Changelog

All notable changes to `suur-things-mcp` are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/); this project uses
[semantic versioning](https://semver.org/).

## [0.4.1] - 2026-05-25

### Security

Hardens the local dashboard's browser boundary. These are local-first issues:
they require the dashboard to be running and the user to load a malicious page
in the same browser. No data is ever exposed to the network.

- **Dashboard reads are now Host-checked.** Added `TrustedHostMiddleware` so any
  request whose `Host` isn't `127.0.0.1`/`localhost` is rejected — closes a
  DNS-rebinding path that could read task titles/notes and linked repo paths.
- **Cross-origin POSTs are properly blocked.** The origin guard now matches the
  full origin (scheme + host + port), not just the hostname. Previously a page
  served from a *different localhost port* could drive state-changing requests
  (config, repo links, open-in-editor, quick-add).
- **Auth token no longer leaks on errors.** The Things auth token is now redacted
  from URL-Scheme error/timeout messages, not only from success responses.
- **Organize agent runs without the token.** `THINGS_AUTH_TOKEN` is stripped from
  the environment of the spawned `claude`/`codex` CLI.

### Changed

- Pinned GitHub Actions to commit SHAs and added Dependabot; committed `uv.lock`
  for reproducible installs.
- Fixed invalid `\s`/`\d` escape sequences in the embedded dashboard JS.

If you installed 0.4.0 or 0.3.0, upgrade with `uv tool upgrade suur-things-mcp`
(or `pip install -U suur-things-mcp`).

## [0.4.0] - 2026-05-25

- Command palette (⌘K), day timeline view, and agent-driven workflows.

## [0.3.0] - 2026-05-25

- First public release.

[0.4.1]: https://github.com/artyomsklyarov/suur-things-mcp/releases/tag/v0.4.1
[0.4.0]: https://github.com/artyomsklyarov/suur-things-mcp/releases/tag/v0.4.0
[0.3.0]: https://github.com/artyomsklyarov/suur-things-mcp/releases/tag/v0.3.0
