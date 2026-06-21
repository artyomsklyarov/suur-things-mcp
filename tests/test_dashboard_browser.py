"""Real-Chromium tests for the dashboard's embedded JavaScript.

The dashboard ships its UI as a JS string inside ``dashboard.py`` with no
JS unit runner, so these load the actual page in a headless browser and assert
the client-side behaviours that pure-Python tests can't reach (XSS escaping,
the quick-add re-entry guard + button feedback).

They skip cleanly when Playwright's Chromium isn't installed, so plain
``uv run pytest`` still passes without ``playwright install``. CI installs the
browser and runs them for real.
"""

import socket
import threading
import time

import pytest

# Skip the whole module if Playwright (the lib) isn't even importable.
pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Error as PWError  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

import uvicorn  # noqa: E402

from suur_things_mcp.dashboard import create_app  # noqa: E402

pytestmark = pytest.mark.browser


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def dashboard_url():
    """Run the real dashboard on a random port in a background uvicorn thread."""
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(port), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.05)
    else:
        pytest.fail("dashboard server did not start")
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def browser():
    """One headless Chromium for the module, or skip if the binary isn't installed."""
    with sync_playwright() as pw:
        try:
            br = pw.chromium.launch()
        except PWError as exc:  # binary missing → skip, don't fail
            pytest.skip(f"Chromium not installed (run `playwright install chromium`): {exc}")
        yield br
        br.close()


@pytest.fixture
def page(browser, dashboard_url):
    pg = browser.new_page()
    pg.goto(dashboard_url, wait_until="domcontentloaded")
    yield pg
    pg.close()


def test_jsarg_neutralizes_apostrophe(page):
    """jsarg() must make an untrusted title safe inside a single-quoted inline
    handler (the v0.8.0 XSS fix) while still round-tripping via decodeURIComponent."""
    payload = "x'+alert(1)+'y"
    out = page.evaluate("(s) => jsarg(s)", payload)
    assert "'" not in out  # the string-delimiter breakout char is gone
    assert page.evaluate("(s) => decodeURIComponent(s)", out) == payload


def test_quickadd_guard_and_feedback(page):
    """createFromCard() locks the Add button + sets CREATING immediately, and a
    second call while in flight is a no-op (no duplicate submit). fetch is stubbed
    so the test creates no real Things task."""
    state = page.evaluate(
        """() => {
            // stub the network so /api/add never reaches the server (no real task)
            window.fetch = (url) => Promise.resolve({ json: () => Promise.resolve({ ok: true, uuid: null }) });
            openCreate('todo');
            document.querySelector('#f-title').value = '__BROWSERTEST__';
            createFromCard();                       // async; sync prelude runs now
            const b = document.querySelector('#ec-add');
            const first = { creating: CREATING, disabled: b.disabled, text: b.textContent };
            createFromCard();                       // re-entry must be ignored
            return { first, stillCreating: CREATING };
        }"""
    )
    assert state["first"]["creating"] is True
    assert state["first"]["disabled"] is True
    assert state["first"]["text"] in ("Adding…", "Adding image…")
    assert state["stillCreating"] is True  # guard held on the second call


def test_page_loads_without_js_exceptions(browser, dashboard_url):
    """The dashboard JS boots without throwing. Only uncaught exceptions
    (pageerror) count — not console logs, which include benign failed-request
    noise that differs between a machine with Things and CI without it."""
    pg = browser.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(dashboard_url, wait_until="networkidle")
    pg.close()
    assert not errors, f"uncaught JS exceptions on load: {errors}"
