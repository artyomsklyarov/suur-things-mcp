"""Real frontend interactions with every API request intercepted before the server.

The existing browser/server fixtures serve the nonce-protected HTML. Synthetic
responses below make these tests independent of Things, tokens and user config.
"""

import copy
import json
from urllib.parse import parse_qs, urlparse

import pytest
from test_dashboard_browser import browser as browser  # noqa: F401
from test_dashboard_browser import dashboard_url as dashboard_url  # noqa: F401

pytestmark = pytest.mark.browser

CONFIG = {
    "boards": [],
    "priority": {},
    "priority_levels": [],
    "area_prefs": {},
    "links": {},
    "prefs": {},
    "attachments": {},
    "timeblocks": {},
}
SIDEBAR = {
    "builtins": [
        {"id": x, "title": x.title(), "count": 0}
        for x in ["inbox", "today", "upcoming", "anytime", "someday", "logbook", "trash"]
    ],
    "areas": [{"uuid": "area", "title": "Work", "projects": [{"uuid": "project", "title": "Book", "progress": 0}]}],
    "arealess": [],
    "tags": [],
}
TASK = {
    "uuid": "task",
    "title": "Write an outline",
    "status": "incomplete",
    "tags": ["writing"],
    "notes": "Useful context",
    "deadline": None,
    "project_title": None,
    "heading_title": None,
    "checklist": [],
}


@pytest.fixture
def ui(browser, dashboard_url):
    page = browser.new_page()
    errors, posts = [], []
    cfg = copy.deepcopy(CONFIG)
    task = copy.deepcopy(TASK)

    def respond(route):
        req = route.request
        url = urlparse(req.url)
        query = parse_qs(url.query)
        if req.method == "POST":
            body = req.post_data_json
            posts.append((url.path, body))
            if url.path == "/api/config":
                cfg.update(body)
                data = {"ok": True, "config": cfg}
            else:
                data = {"ok": True}
        elif url.path == "/api/config":
            data = {"ok": True, "config": cfg}
        elif url.path == "/api/sidebar":
            data = {"ok": True, "auth": True, "sidebar": SIDEBAR}
        elif url.path == "/api/items":
            item_id = query.get("id", ["today"])[0]
            data = {"ok": True, "kind": "builtin", "items": [] if item_id == "inbox" else [task]}
        elif url.path == "/api/item":
            data = {"ok": True, "item": task}
        elif url.path == "/api/search":
            data = {"ok": True, "items": []}
        elif url.path == "/api/version":
            data = {"ok": True, "version": page.evaluate("() => SERVER_VERSION")}
        else:
            data = {"ok": True}
        route.fulfill(content_type="application/json", body=json.dumps(data))

    page.route("**/api/**", respond)
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(dashboard_url, wait_until="networkidle")
    page.locator(".row").wait_for()
    yield {"page": page, "posts": posts, "config": cfg, "task": task, "errors": errors}
    page.close()
    assert not errors, f"uncaught frontend exceptions: {errors}"


def test_navigation_cards_and_empty_inbox(ui):
    page = ui["page"]
    page.locator("#vt-cards").click()
    page.locator(".taskcard").wait_for()
    assert page.locator(".tc-title").inner_text() == TASK["title"]
    page.locator('#side-nav [data-id="inbox"]').click()
    page.locator("#content .empty").wait_for()
    assert "Inbox Zero" in page.locator("#content").inner_text()
    page.get_by_role("button", name="Add a task").click()
    page.locator("#edit-overlay.show").wait_for()


def test_hostile_task_title_is_literal_in_list_and_card(ui):
    page = ui["page"]
    payload = '<img src=x onerror="alert(1)"> & <script>alert(2)</script>'
    ui["task"]["title"] = payload
    page.evaluate("() => route()")
    page.wait_for_function("(text) => document.querySelector('#content').textContent.includes(text)", arg=payload)
    assert page.locator("#content img, #content script").count() == 0
    page.locator("#vt-cards").click()
    page.locator(".tc-title").wait_for()
    assert page.locator(".tc-title").inner_text() == payload
    assert page.locator("#content img, #content script").count() == 0


def test_palette_keyboard_open_move_and_close(ui):
    page = ui["page"]
    page.keyboard.press("Control+k")
    page.locator("#cmdk.show").wait_for()
    page.locator("#cmdk-input").wait_for(state="visible")
    page.keyboard.press("ArrowDown")
    assert page.evaluate("() => CK_SEL") == 1
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.querySelector('#cmdk').classList.contains('show')")


def test_preferences_posts_only_owned_section(ui):
    page = ui["page"]
    page.locator("#prefs-btn").click()
    page.locator("#pf-editor").fill("cursor")
    page.locator("#pf-terminal").fill("Ghostty")
    page.locator("#pf-save").click()
    page.wait_for_function("() => !document.querySelector('#prefs-overlay').classList.contains('show')")
    assert ui["posts"] == [("/api/config", {"prefs": {"editor": "cursor", "terminal": "Ghostty"}})]
