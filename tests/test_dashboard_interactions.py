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


@pytest.mark.parametrize("value", ["[broken", "{}", "null"])
def test_startup_tolerates_corrupt_collapsed_state(ui, value):
    page = ui["page"]
    page.set_default_timeout(2000)
    page.add_init_script(f"localStorage.setItem('collapsed-areas', {json.dumps(value)});")
    page.reload(wait_until="networkidle")
    page.locator(".row").wait_for()


def test_startup_tolerates_blocked_browser_storage(ui):
    page = ui["page"]
    page.set_default_timeout(2000)
    page.add_init_script("Object.defineProperty(window, 'localStorage', {get(){throw new Error('storage blocked');}});")
    page.reload(wait_until="networkidle")
    page.locator(".row").wait_for()
    page.locator("#theme").click()


def test_config_failure_keeps_tasks_and_prevents_overlay_overwrite(ui):
    page = ui["page"]
    page.set_default_timeout(2000)

    def fail(route):
        route.fulfill(json={"ok": False, "error": "temporary failure"})

    page.route("**/api/config", fail)
    page.reload(wait_until="networkidle")
    page.locator(".row").wait_for()
    assert page.locator("#config-error").is_visible()
    page.on("dialog", lambda dialog: dialog.dismiss())
    page.evaluate("() => saveConfig()")
    assert ui["posts"] == []
    page.unroute("**/api/config", fail)
    page.locator("#config-retry").click()
    page.wait_for_function("() => document.querySelector('#config-error').hidden")


def test_sidebar_error_preserves_navigation_structure_and_can_retry(ui):
    page = ui["page"]
    page.set_default_timeout(2000)

    def fail(route):
        route.fulfill(json={"ok": False, "error": "temporary failure", "sidebar": {}})

    page.route("**/api/sidebar", fail)
    page.reload(wait_until="networkidle")
    assert page.locator("#side-nav").count() == 1
    assert page.locator("#about-link").count() == 1
    page.unroute("**/api/sidebar", fail)
    page.locator("#sidebar-retry").click()
    page.locator('#side-nav [data-id="today"]').wait_for()
    page.locator(".row").wait_for()


def test_dialog_focus_is_contained_and_returns_to_trigger(ui):
    page = ui["page"]
    page.locator("#prefs-btn").click()
    page.wait_for_function("() => document.activeElement.id === 'pf-editor'", timeout=2000)
    assert page.get_by_role("dialog", name="Preferences").is_visible()
    assert page.get_by_label("Editor command", exact=False).count() == 1
    page.keyboard.press("Shift+Tab")
    assert page.evaluate("() => document.activeElement.id") == "pf-cancel"
    page.keyboard.press("Tab")
    assert page.evaluate("() => document.activeElement.id") == "pf-editor"
    assert page.locator(".views").evaluate("el => el.inert") is True
    page.keyboard.press("Escape")
    assert page.evaluate("() => document.activeElement.id") == "prefs-btn"
    assert page.locator(".views").evaluate("el => el.inert") is False


def test_escape_closes_only_top_dialog(ui):
    page = ui["page"]
    page.locator("#prefs-btn").click()
    page.evaluate("() => openCmdk()")
    page.locator("#cmdk.show").wait_for()
    page.keyboard.press("Escape")
    assert page.locator("#prefs-overlay").evaluate("el => el.classList.contains('show')") is True
    assert page.evaluate("() => document.activeElement.id") == "pf-editor"
    page.keyboard.press("Escape")
    assert page.evaluate("() => document.activeElement.id") == "prefs-btn"


def test_create_dialog_has_named_fields_and_keyboard_close(ui):
    page = ui["page"]
    page.locator("#add-btn").click()
    assert page.get_by_role("dialog", name="New to-do", exact=False).is_visible()
    assert page.get_by_label("Task title").count() == 1
    assert page.get_by_label("Notes", exact=True).count() == 1
    page.get_by_role("button", name="Close (saves changes)").focus()
    page.keyboard.press("Enter")
    assert not page.locator("#edit-overlay").evaluate("el => el.classList.contains('show')")
    assert ui["posts"] == []


def test_sidebar_filter_and_task_actions_work_from_keyboard(ui):
    page = ui["page"]
    inbox = page.locator('#side-nav [data-id="inbox"]')
    assert inbox.get_attribute("tabindex") == "0"
    inbox.focus()
    page.keyboard.press("Enter")
    page.locator("#content .empty").wait_for()
    page.locator('#side-nav [data-id="today"]').focus()
    page.keyboard.press("Enter")
    page.locator(".row .title").wait_for()
    tag = page.get_by_role("button", name="writing", exact=True)
    tag.focus()
    page.keyboard.press("Space")
    assert tag.get_attribute("aria-pressed") == "true"
    page.get_by_role("button", name=TASK["title"], exact=True).focus()
    page.keyboard.press("Enter")
    page.get_by_role("dialog", name="Edit task").wait_for()
    page.keyboard.press("Escape")
    checkbox = page.get_by_role("checkbox", name="Complete " + TASK["title"], exact=True)
    checkbox.focus()
    page.keyboard.press("Space")
    page.wait_for_function("() => document.querySelector('.row .box').getAttribute('aria-checked') === 'true'")
    assert ui["posts"] == [("/api/update", {"id": "task", "completed": True})]


def test_palette_exposes_active_option_and_expandable_area_state(ui):
    page = ui["page"]
    chev = page.get_by_role("button", name="Toggle Work", exact=True)
    assert chev.get_attribute("aria-expanded") == "true"
    chev.focus()
    page.keyboard.press("Space")
    page.wait_for_function("() => !document.querySelector('#side-nav [data-id=project]')", timeout=2000)
    assert page.get_by_role("button", name="Toggle Work", exact=True).get_attribute("aria-expanded") == "false"
    page.keyboard.press("Control+k")
    page.locator("#cmdk.show").wait_for()
    combobox = page.get_by_role("combobox", name="Search tasks or commands")
    page.keyboard.press("ArrowDown")
    selected_id = combobox.get_attribute("aria-activedescendant")
    assert selected_id
    assert page.locator("#" + selected_id).get_attribute("aria-selected") == "true"


def test_standalone_project_resolves_and_navigates(ui):
    page = ui["page"]
    page.evaluate(
        "() => { SIDEBAR.arealess.push({uuid:'standalone',title:'Independent project',progress:0}); renderSidebar(); }"
    )
    result = page.evaluate("() => resolveList('standalone')")
    assert result == {"id": "standalone", "icon": "", "title": "Independent project", "kind": "project"}
    page.locator('#side-nav [data-id="standalone"]').click()
    page.wait_for_function(
        "() => document.querySelector('#head-title').textContent === 'Independent project'", timeout=2000
    )
    assert page.url.endswith("#l/standalone")


def test_compact_preview_uses_window_width_and_navigation_can_close(ui):
    page = ui["page"]
    page.set_default_timeout(3000)
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(page.url.split("#")[0] + "?compact=1", wait_until="networkidle")
    assert page.locator(".main").bounding_box()["width"] == 390
    toggle = page.get_by_role("button", name="Open navigation", exact=True)
    toggle.click()
    assert toggle.get_attribute("aria-expanded") == "true"
    assert page.locator(".main").evaluate("el => el.inert") is True
    page.keyboard.press("Escape")
    assert toggle.get_attribute("aria-expanded") == "false"
    assert page.evaluate("() => document.activeElement.id") == "nav-toggle"
    toggle.click()
    page.locator('#side-nav [data-id="inbox"]').click()
    page.locator("#content .empty").wait_for()
    assert toggle.get_attribute("aria-expanded") == "false"
    assert page.locator(".main").evaluate("el => el.inert") is False
    assert page.locator("#vt-timeline").bounding_box()["x"] < 390
