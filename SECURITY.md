# Security Policy

`suur-things-mcp` is a local-first, single-user macOS tool. It reads the Things 3
database read-only and writes only through Things' documented URL Scheme. There is
no server-side component, no network listener beyond a `127.0.0.1`-bound dashboard,
and no destructive operation (complete / cancel / move are all reversible in Things).

## Reporting a vulnerability

Please report security issues **privately** — do not open a public issue for
anything exploitable.

- Preferred: open a [GitHub private security advisory](https://github.com/artyomsklyarov/suur-things-mcp/security/advisories/new).
- Or email the maintainer via the contact on [suur.io](https://suur.io).

Include the version (`pip show suur-things-mcp`), your OS, and a minimal
reproduction. I'll acknowledge within a few days and aim to ship a fix or
mitigation before any public disclosure.

## Scope

The defenses in this tool protect the **browser boundary** of the local dashboard.
They are not a sandbox against other processes on your machine.

In scope (please report):

- A web page in your browser reading or writing your Things data via the dashboard
  (DNS-rebinding, cross-origin / cross-port POST, CSRF).
- Command or URL injection through any MCP tool or dashboard endpoint.
- XSS in the dashboard.
- Leakage of `THINGS_AUTH_TOKEN` into logs, tool results, or error messages.
- Supply-chain issues in the build/release pipeline.

Out of scope (known and accepted for a local single-user tool):

- Attacks requiring local filesystem or process access — such an attacker already
  has more capability than this tool exposes (e.g. reading the token file directly,
  or seeing the token in `open`'s process arguments via `ps`).
- Prompt injection via task content influencing *your own* connected agent. Task
  titles/notes are returned to your agent like any MCP server's content; the bundled
  prompts treat them as data, and the tool has no hard-delete. Treat tasks from
  untrusted sources with the same caution as any other input to your agent.

## Supported versions

The latest released version on PyPI receives security fixes. This is a young
project (0.x); please stay current.
