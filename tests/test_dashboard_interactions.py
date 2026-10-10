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


@pytest.mark.parametrize("width", [320, 390, 768])
def test_narrow_views_fit_and_resize_restores_desktop(ui, width):
    page = ui["page"]
    page.set_default_timeout(3000)
    page.set_viewport_size({"width": width, "height": 844})
    page.reload(wait_until="networkidle")
    assert page.locator(".main").bounding_box()["width"] == width
    assert page.locator("#sidebar").evaluate("el => el.inert") is True
    for view in ["matrix", "levels", "cards", "timeline", "list"]:
        page.locator("#vt-" + view).click()
        page.wait_for_function("v => MODE === v", arg=view)
        page.wait_for_timeout(100)
        geometry = page.locator("#content").evaluate("el => ({width:el.clientWidth, scroll:el.scrollWidth})")
        assert geometry["scroll"] <= geometry["width"] + 1, (width, view, geometry)
    page.locator("#nav-toggle").click()
    page.set_viewport_size({"width": 1440, "height": 900})
    page.wait_for_function("() => !document.querySelector('#sidebar').inert && !document.querySelector('.main').inert")
    assert page.locator(".main").evaluate("el => el.inert") is False
    assert page.locator("#nav-toggle").is_visible() is False
    assert page.locator("#sidebar").bounding_box()["width"] == 272


def _contrast(foreground, background):
    def luminance(rgb):
        channels = [x / 255 for x in rgb]
        linear = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in channels]
        return sum(x * weight for x, weight in zip(linear, [0.2126, 0.7152, 0.0722], strict=True))

    a, b = sorted([luminance(foreground), luminance(background)])
    return (b + 0.05) / (a + 0.05)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_small_text_and_primary_controls_have_sufficient_contrast(ui, theme):
    page = ui["page"]
    page.evaluate("(theme) => document.documentElement.dataset.theme = theme", theme)
    page.wait_for_timeout(250)
    samples = []

    def measure(selectors):
        for selector in selectors:
            pairs = page.locator(selector).evaluate_all("""els => els.map(el => {
                const rgb = value => value.match(/[\\d.]+/g).map(Number).slice(0, 3);
                let parent = el, bg;
                while(parent) {
                    bg = getComputedStyle(parent).backgroundColor;
                    if(bg !== 'rgba(0, 0, 0, 0)') break;
                    parent = parent.parentElement;
                }
                return [rgb(getComputedStyle(el).color), rgb(bg)];
            })""")
            assert pairs, selector
            samples.extend((selector, _contrast(fg, bg)) for fg, bg in pairs)

    measure([".nav-item .count", ".group-head"])
    page.locator("#vt-matrix").click()
    page.locator(".quad-head").first.wait_for()
    measure([".quad-head .qt", ".quad-head .qs", ".pri-pool .col-head"])
    page.locator("#vt-levels").click()
    page.locator(".lvl-head").first.wait_for()
    measure([".lvl-head .lt", ".lvl-head .ls", ".lvl-mapnote"])
    page.locator("#prefs-btn").click()
    page.wait_for_timeout(250)
    measure(["#prefs-overlay .hint", "#prefs-overlay .field label", "#pf-save", "#pf-cancel"])
    print(f"{theme} contrast ratios: {samples}")
    assert all(ratio >= 4.5 for _, ratio in samples), samples


def test_preferences_editor_save_preserves_organizer_settings(ui):
    page = ui["page"]
    ui["config"]["prefs"] = {"agent": "codex", "agent_model": "custom-model"}
    page.evaluate("() => loadConfig()")
    page.locator("#prefs-btn").click()
    page.locator("#pf-editor").fill("cursor")
    page.locator("#pf-save").click()
    page.wait_for_function("() => !document.querySelector('#prefs-overlay').classList.contains('show')")
    assert ui["posts"] == [
        (
            "/api/config",
            {"prefs": {"agent": "codex", "agent_model": "custom-model", "editor": "cursor", "terminal": ""}},
        )
    ]


@pytest.mark.parametrize(
    "source,target",
    [("list", "inbox"), ("list", "about"), ("board", "inbox"), ("priority", "about"), ("levels", "inbox")],
)
def test_delayed_view_response_cannot_replace_latest_navigation(ui, source, target):
    page = ui["page"]
    page.evaluate("""() => {
        const original = window.fetch;
        window.fetch = (url, options) => {
            if(!window.releaseView && (url.startsWith('/api/items') || url.startsWith('/api/board'))) {
                return new Promise(resolve => window.releaseView = () => resolve({ok:true, json:async()=>({ok:true, kind:'builtin', items:[{uuid:'stale',title:'Stale response',tags:[]}], columns:[{title:'Stale column',name:'old',cards:[]}]})}));
            }
            return original(url, options);
        };
    }""")
    page.evaluate(
        """source => {
        if(source==='list') renderList(resolveList('today'));
        else if(source==='board') renderBoard('fixture');
        else if(source==='priority') renderPriority();
        else renderLevels();
    }""",
        source,
    )
    page.wait_for_function("() => !!window.releaseView")
    if target == "about":
        page.evaluate("() => renderAbout()")
        expected = page.locator("#content").inner_text()
    else:
        page.evaluate("() => renderList(resolveList('inbox'))")
        page.locator("#content .empty").wait_for()
        expected = page.locator("#content").inner_text()
    page.evaluate("() => window.releaseView()")
    page.wait_for_timeout(100)
    assert page.locator("#content").inner_text() == expected
    assert "Stale" not in page.locator("#content").inner_text()
    if target == "inbox":
        assert page.evaluate("() => LIST_ITEMS") == []


def _fixture_board(ui):
    page = ui["page"]
    ui["config"]["boards"] = [
        {
            "id": "fixture",
            "name": "Fixture board",
            "columns": ["Backlog", "Done"],
            "placements": {},
            "include_areas": [],
            "include_projects": [],
        }
    ]
    card = {"id": "project", "title": "Book", "kind": "project", "progress": 0, "open": 1, "total": 1, "repos": []}

    def respond(route):
        placement = ui["config"]["boards"][0]["placements"].get("project")
        route.fulfill(
            json={
                "ok": True,
                "auth": True,
                "columns": [
                    {"name": col, "title": col, "cards": [card] if col == placement else []}
                    for col in [None, "Backlog", "Done"]
                ],
            }
        )

    page.route("**/api/board?*", respond)
    page.evaluate("() => loadConfig()")
    page.evaluate("() => renderBoard('fixture')")
    page.locator(".card").wait_for()


def _drop(page, selector, item_id, y=None):
    page.evaluate(
        """arg => {
        const target=document.querySelector(arg.selector), data=new DataTransfer();
        data.setData('text/id',arg.id);
        target.dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:data,clientY:arg.y||0}));
    }""",
        {"selector": selector, "id": item_id, "y": y},
    )


def test_matrix_drag_preserves_other_priority_entries(ui):
    page = ui["page"]
    ui["config"]["priority"] = {"other": "delegate"}
    page.evaluate("() => loadConfig()")
    page.locator("#vt-matrix").click()
    page.locator(".q-do").wait_for()
    _drop(page, ".q-do", "task")
    page.wait_for_function("() => CONFIG.priority.task==='do'")
    page.locator(".q-do .pcard").wait_for()
    assert ui["posts"][-1][1]["priority"] == {"other": "delegate", "task": "do"}


def test_level_drag_replaces_only_mapped_tags(ui):
    page = ui["page"]
    ui["config"]["priority_levels"] = [{"label": "P1", "tags": ["urgent"]}, {"label": "P2", "tags": ["later"]}]
    ui["task"]["tags"] = ["writing", "later"]
    page.evaluate("() => loadConfig()")
    page.locator("#vt-levels").click()
    page.locator(".lvl-2 .pcard").wait_for()
    _drop(page, ".lvl-1", "task")
    page.wait_for_function("() => LIST_ITEMS[0].tags.includes('urgent')")
    assert ui["posts"] == [("/api/update", {"id": "task", "tags": ["writing", "urgent"]})]


def test_level_drag_without_auth_never_posts(ui):
    page = ui["page"]
    page.evaluate("() => AUTH=false")
    page.locator("#vt-levels").click()
    page.locator(".lvl-1").wait_for()
    page.on("dialog", lambda dialog: dialog.dismiss())
    _drop(page, ".lvl-1", "task")
    page.wait_for_timeout(100)
    assert ui["posts"] == []


def test_board_drag_uses_existing_stages(ui):
    _fixture_board(ui)
    page = ui["page"]
    _drop(page, ".col:last-child", "project")
    page.wait_for_function("() => CONFIG.boards[0].placements.project==='Done'")
    page.locator(".col:last-child .card").wait_for()
    assert ui["posts"][-1][1]["boards"][0]["placements"] == {"project": "Done"}


def test_timeline_drag_places_and_unschedules_without_task_mutation(ui):
    page = ui["page"]
    page.locator("#vt-timeline").click()
    page.locator(".tl-grid").wait_for()
    y = page.locator(".tl-grid").bounding_box()["y"] + 4.5 * 44
    _drop(page, ".tl-grid", "task", y)
    page.locator(".tl-block").wait_for()
    assert ui["posts"][-1][1]["timeblocks"]["task"]["start"] == "10:30"
    _drop(page, ".tl-pool", "task")
    page.wait_for_function("() => !CONFIG.timeblocks.task")
    page.locator(".pcard").wait_for()
    assert ui["posts"][-1] == ("/api/config", {"timeblocks": {}})
    assert all(path == "/api/config" for path, _ in ui["posts"])


def _enable_placement_preview(page):
    page.set_default_timeout(3000)
    page.goto(page.url.split("#")[0].split("?")[0] + "?placement=1#l/today", wait_until="networkidle")
    page.locator(".row").wait_for()


def test_keyboard_matrix_picker_preserves_priority_and_focus(ui):
    page = ui["page"]
    _enable_placement_preview(page)
    ui["config"]["priority"] = {"other": "delegate"}
    page.evaluate("() => loadConfig()")
    page.locator("#vt-matrix").click()
    picker = page.get_by_label("Quadrant for Write an outline")
    picker.focus()
    picker.select_option("do")
    page.locator(".q-do .pcard").wait_for()
    assert ui["posts"] == [("/api/config", {"priority": {"other": "delegate", "task": "do"}})]
    assert picker.evaluate("el => document.activeElement === el") is True
    title = page.locator(".q-do .pt")
    title.focus()
    page.keyboard.press("Enter")
    page.locator("#edit-overlay.show").wait_for()


def test_keyboard_level_picker_preserves_other_tags_and_disables_without_auth(ui):
    page = ui["page"]
    _enable_placement_preview(page)
    ui["config"]["priority_levels"] = [{"label": "P1", "tags": ["urgent"]}, {"label": "P2", "tags": ["later"]}]
    ui["task"]["tags"] = ["writing", "later"]
    page.evaluate("() => loadConfig()")
    page.locator("#vt-levels").click()
    picker = page.get_by_label("Priority level for Write an outline")
    picker.focus()
    picker.select_option("0")
    page.locator(".lvl-1 .pcard").wait_for()
    assert ui["posts"] == [("/api/update", {"id": "task", "tags": ["writing", "urgent"]})]
    assert picker.evaluate("el => document.activeElement === el") is True
    page.evaluate("() => {AUTH=false;renderLevelBands();}")
    assert picker.is_disabled()


def test_keyboard_board_picker_uses_existing_stages_and_keeps_focus(ui):
    page = ui["page"]
    _enable_placement_preview(page)
    _fixture_board(ui)
    picker = page.get_by_label("Stage for Book")
    picker.focus()
    picker.select_option("Done")
    page.locator(".col:last-child .card").wait_for()
    assert ui["posts"][-1][1]["boards"][0]["placements"] == {"project": "Done"}
    assert set(ui["posts"][-1][1]) == {"boards"}
    assert picker.evaluate("el => document.activeElement === el") is True
    title = page.locator(".card .ct")
    title.focus()
    page.keyboard.press("Enter")
    page.wait_for_function("() => location.hash === '#l/project'")


def test_failed_matrix_picker_keeps_previous_placement(ui):
    page = ui["page"]
    _enable_placement_preview(page)
    page.locator("#vt-matrix").click()
    page.route("**/api/config", lambda route: route.fulfill(json={"ok": False, "error": "fixture failure"}))
    page.on("dialog", lambda dialog: dialog.dismiss())
    picker = page.get_by_label("Quadrant for Write an outline")
    picker.select_option("do")
    page.wait_for_function("() => !document.querySelector('.placement').disabled")
    assert picker.input_value() == ""
    assert page.evaluate("() => CONFIG.priority") == {}
    assert page.locator(".pri-pool .pcard").count() == 1


def test_priority_card_completion_works_from_keyboard(ui):
    page = ui["page"]
    _enable_placement_preview(page)
    page.locator("#vt-matrix").click()
    check = page.get_by_role("checkbox", name="Complete Write an outline")
    check.focus()
    page.keyboard.press("Space")
    page.locator(".pcard").wait_for(state="detached")
    assert ui["posts"] == [("/api/update", {"id": "task", "completed": True})]


def _open_slot_preview(ui):
    page = ui["page"]
    _enable_placement_preview(page)
    page.locator("#vt-timeline").click()
    page.get_by_role("button", name="Schedule Write an outline", exact=True).click()
    page.get_by_role("dialog", name="Schedule · Write an outline").wait_for()
    return page


def test_keyboard_timeline_schedule_change_and_unschedule(ui):
    page = _open_slot_preview(ui)
    assert page.get_by_label("Start time").evaluate("el => document.activeElement === el")
    page.get_by_label("Start time").fill("10:30")
    page.get_by_label("Duration (minutes)").fill("60")
    page.get_by_role("button", name="Save time block", exact=True).click()
    page.locator(".tl-block").wait_for()
    assert ui["posts"][-1] == (
        "/api/config",
        {"timeblocks": {"task": {"date": page.evaluate("() => todayStr()"), "start": "10:30", "mins": 60}}},
    )
    button = page.get_by_role("button", name="Schedule Write an outline", exact=True)
    assert button.evaluate("el => document.activeElement === el")
    button.click()
    assert page.get_by_label("Start time").input_value() == "10:30"
    page.get_by_role("button", name="Unscheduled", exact=True).click()
    page.locator(".tl-block").wait_for(state="detached")
    assert ui["posts"][-1] == ("/api/config", {"timeblocks": {}})
    assert all(path == "/api/config" for path, _ in ui["posts"])


def test_timeline_dialog_cancel_and_invalid_duration_do_not_write(ui):
    page = _open_slot_preview(ui)
    page.get_by_label("Duration (minutes)").fill("0")
    page.get_by_role("button", name="Save time block", exact=True).click()
    assert page.locator("#slot-overlay.show").is_visible()
    assert ui["posts"] == []
    page.keyboard.press("Escape")
    assert not page.locator("#slot-overlay").evaluate("el => el.classList.contains('show')")
    assert page.get_by_role("button", name="Schedule Write an outline", exact=True).evaluate(
        "el => document.activeElement === el"
    )


def test_timeline_failed_save_keeps_dialog_and_previous_blocks(ui):
    page = _open_slot_preview(ui)
    page.route("**/api/config", lambda route: route.fulfill(json={"ok": False, "error": "fixture failed save"}))
    page.on("dialog", lambda dialog: dialog.dismiss())
    page.get_by_role("button", name="Save time block", exact=True).click()
    page.wait_for_function("() => !document.querySelector('#slot-save').disabled")
    assert page.locator("#slot-overlay.show").is_visible()
    assert page.evaluate("() => CONFIG.timeblocks") == {}


def test_timeline_pending_save_does_not_replace_new_navigation(ui):
    page = _open_slot_preview(ui)
    page.evaluate("""() => {
        const original=window.fetch;
        window.fetch=(url,options)=>url==='/api/config'&&options?.method==='POST'
            ?new Promise(resolve=>window.finishSlot=()=>resolve({ok:true,json:async()=>({ok:true,config:CONFIG})}))
            :original(url,options);
    }""")
    page.get_by_role("button", name="Save time block", exact=True).click()
    page.wait_for_function("() => !!window.finishSlot")
    page.keyboard.press("Escape")
    page.evaluate("() => renderAbout()")
    expected = page.locator("#content").inner_text()
    page.evaluate("() => window.finishSlot()")
    page.wait_for_timeout(100)
    assert page.locator("#content").inner_text() == expected
    assert not page.locator("#slot-overlay").evaluate("el => el.classList.contains('show')")


def test_timeline_preserves_unrelated_blocks_and_rejects_end_after_day(ui):
    ui["config"]["timeblocks"] = {"other": {"date": "2026-01-01", "start": "12:00", "mins": 30}}
    page = _open_slot_preview(ui)
    page.get_by_label("Start time").fill("22:45")
    page.get_by_label("Duration (minutes)").fill("60")
    page.get_by_role("button", name="Save time block", exact=True).click()
    assert ui["posts"] == []
    page.get_by_label("Start time").fill("10:30")
    page.get_by_role("button", name="Save time block", exact=True).click()
    page.locator(".tl-block").wait_for()
    assert ui["posts"][-1][1]["timeblocks"]["other"] == {"date": "2026-01-01", "start": "12:00", "mins": 30}


@pytest.mark.parametrize("status", ["completed", "canceled"])
def test_advanced_terminal_tasks_have_checked_disabled_completion(ui, status):
    ui["task"]["status"] = status
    page = ui["page"]
    _enable_placement_preview(page)
    page.locator("#vt-matrix").click()
    check = page.get_by_role("checkbox", name="Complete Write an outline")
    assert check.get_attribute("aria-checked") == "true"
    assert check.get_attribute("aria-disabled") == "true"
    assert check.get_attribute("tabindex") != "0"
    check.click(force=True)
    page.wait_for_timeout(100)
    assert ui["posts"] == []


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("selected", [False, True])
def test_checkbox_boundary_is_visible_against_its_background(ui, theme, selected):
    page = ui["page"]
    page.evaluate(
        'arg => {applyTheme(arg.theme); document.querySelector(".row").classList.toggle("selected",arg.selected);}',
        {"theme": theme, "selected": selected},
    )
    page.wait_for_timeout(250)
    fg, bg = page.locator(".row .box").evaluate("""el => {
        const rgb=value=>value.match(/[\\d.]+/g).map(Number).slice(0,3);
        let parent=el, bg;
        while(parent){bg=getComputedStyle(parent).backgroundColor;if(bg!=='rgba(0, 0, 0, 0)')break;parent=parent.parentElement;}
        return [rgb(getComputedStyle(el).borderColor),rgb(bg)];
    }""")
    ratio = _contrast(fg, bg)
    print(theme, selected, ratio)
    assert ratio >= 3


def test_placement_controls_default_on_with_diagnostic_opt_out(ui):
    page = ui["page"]
    page.set_default_timeout(3000)
    page.locator("#vt-matrix").click()
    page.get_by_label("Quadrant for Write an outline").wait_for()
    page.goto(page.url.split("?")[0].split("#")[0] + "?placement=0#l/today", wait_until="networkidle")
    page.locator("#vt-matrix").click()
    page.locator(".pcard").wait_for()
    assert page.locator(".placement").count() == 0


@pytest.mark.parametrize("width", [320, 768])
def test_scheduled_slot_dialog_fits_narrow_windows(ui, width):
    page = ui["page"]
    page.set_viewport_size({"width": width, "height": 844})
    ui["config"]["timeblocks"] = {"task": {"date": page.evaluate("() => todayStr()"), "start": "10:30", "mins": 60}}
    page = _open_slot_preview(ui)
    assert page.get_by_role("button", name="Unscheduled", exact=True).is_visible()
    geometry = page.locator("#slot-overlay .panel").evaluate("el=>({width:el.clientWidth,scroll:el.scrollWidth})")
    assert geometry["scroll"] <= geometry["width"]
    assert page.locator("#slot-overlay .panel").bounding_box()["width"] <= width
