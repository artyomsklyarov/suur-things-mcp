"""Things URL Scheme — the *only* supported way to write to Things.

Cultured Code's own AI-integration guidance is explicit: writing directly to
the SQLite database is unsafe and can corrupt it. All mutations here go through
the documented URL Scheme (``things:///...``), executed via macOS ``open``.

Docs: https://culturedcode.com/things/support/articles/2803573/
"""

from __future__ import annotations

import subprocess
from typing import Iterable
from urllib.parse import quote

SCHEME = "things:///"

# Commands that mutate existing items require the auth token from
# Things → Settings → General → "Enable Things URLs" → Manage.
AUTH_REQUIRED = {"update", "update-project"}


class ThingsURLError(RuntimeError):
    """Raised when a URL command cannot be built or executed."""


def _encode(value: str) -> str:
    # Encode everything except nothing — keep it simple and correct.
    # Newlines (%0A) and commas survive quote() with safe="".
    return quote(str(value), safe="")


def _join_lines(items: Iterable[str]) -> str:
    """Newline-joined value for titles / checklist-items / to-dos params."""
    return "\n".join(str(i) for i in items)


def _join_commas(items: Iterable[str]) -> str:
    """Comma-joined value for tags / filters params."""
    return ",".join(str(i) for i in items)


def build_url(command: str, params: dict | None = None) -> str:
    """Build a ``things:///<command>?...`` URL with proper encoding.

    ``None`` values are dropped. ``bool`` values become ``true``/``false``.
    Empty-string values are kept (used to *clear* fields, e.g. ``deadline=``).
    """
    params = params or {}
    parts: list[str] = []
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            value = "true" if value else "false"
        parts.append(f"{key}={_encode(value)}")
    query = "&".join(parts)
    return f"{SCHEME}{command}" + (f"?{query}" if query else "")


def run_url(url: str) -> None:
    """Execute a Things URL via ``open -g`` (background, no window steal)."""
    try:
        result = subprocess.run(
            ["open", "-g", url],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError as exc:  # pragma: no cover - macOS always has open
        raise ThingsURLError("`open` not found — this MCP server requires macOS.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ThingsURLError(f"Timed out launching Things for: {url}") from exc
    if result.returncode != 0:
        raise ThingsURLError(
            f"`open` failed (exit {result.returncode}) for {url}: {result.stderr.strip()}"
        )


def execute(
    command: str,
    params: dict,
    auth_token: str | None = None,
    requires_auth: bool | None = None,
) -> str:
    """Build + run a command, injecting the auth token when required.

    ``requires_auth`` overrides the default per-command rule — needed for the
    ``json`` command, whose token requirement depends on whether the batch
    contains any update operations.

    Returns the executed URL (with the token redacted) for confirmation.
    """
    params = dict(params)
    needs_auth = (command in AUTH_REQUIRED) if requires_auth is None else requires_auth
    if needs_auth:
        if not auth_token:
            raise ThingsURLError(
                f"The '{command}' command modifies existing items and requires an "
                "auth token. Set THINGS_AUTH_TOKEN in the server environment. Get it "
                "from Things → Settings → General → Enable Things URLs → Manage."
            )
        params["auth-token"] = auth_token

    url = build_url(command, params)
    run_url(url)

    # Redact the token before returning to the model.
    if auth_token:
        url = url.replace(_encode(auth_token), "***").replace(auth_token, "***")
    return url
