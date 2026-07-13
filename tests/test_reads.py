"""reads.py against the fixture Things database (tests/conftest.py).

These run everywhere, including CI on Linux — before this fixture existed, all
read-layer logic (overview digest, sidebar, area roll-up, board cards) was only
exercised on a Mac with Things installed, i.e. never in CI.
"""

from suur_things_mcp import reads


def _titles(items):
    return {i["title"] for i in items}


def test_builtin_lists(things_db):
    assert _titles(reads.inbox()) == {"Sort the mail"}
    assert "Write the report" in _titles(reads.today())
    assert "Book flights" in _titles(reads.upcoming())
    assert "Learn woodworking" in _titles(reads.someday())
    assert _titles(reads.trash()) == {"Old junk"}
    assert "Ship v1" in _titles(reads.logbook())
    assert _titles(reads.deadlines()) == {"Pay invoice"}


def test_search_and_get(things_db):
    assert _titles(reads.search("report")) == {"Write the report"}
    item = reads.get("todo-inproj")
    assert item["title"] == "Draft outline"
    assert [c["title"] for c in item.get("checklist", [])] == ["Chapter list"]


def test_find_by_exact_title(things_db):
    rows = reads.find_by_exact_title("Write the report")
    assert [r["uuid"] for r in rows] == ["todo-today"]
    # exact means exact — and trashed rows never match
    assert reads.find_by_exact_title("Write the") == []
    assert reads.find_by_exact_title("Old junk") == []


def test_overview_digest(things_db):
    ov = reads.overview()
    assert ov["counts"]["inbox"] == 1
    assert ov["counts"]["overdue"] == 1
    assert ov["overdue"][0]["uuid"] == "todo-overdue"
    # proj-book has an open task; proj-empty has none → flagged as stalled
    stalled = {p["uuid"] for p in ov["projects_without_next_action"]}
    assert stalled == {"proj-empty"}
    assert {t["uuid"] for t in ov["recent_completed"]} == {"todo-done"}


def test_sidebar_tree(things_db):
    sb = reads.sidebar()
    by_id = {b["id"]: b for b in sb["builtins"]}
    assert by_id["inbox"]["count"] == 1
    work = next(a for a in sb["areas"] if a["uuid"] == "area-work")
    assert {p["uuid"] for p in work["projects"]} == {"proj-book"}
    assert {p["uuid"] for p in sb["arealess"]} == {"proj-empty"}


def test_area_rollup(things_db):
    # With roll-up: the area's loose to-do plus its projects' open tasks.
    rolled = reads.list_items("area-work", rollup=True)
    assert rolled["kind"] == "area"
    assert _titles(rolled["items"]) == {"Area loose task", "Write the report", "Draft outline"}
    # Without: only the loose to-dos.
    flat = reads.list_items("area-work", rollup=False)
    assert _titles(flat["items"]) == {"Area loose task", "Write the report"}


def test_list_items_project_and_builtin(things_db):
    proj = reads.list_items("proj-book")
    assert proj["kind"] == "project"
    assert _titles(proj["items"]) == {"Draft outline"}
    # Built-in lists render to-dos only (projects stay in the sidebar).
    anytime = reads.list_items("anytime")
    assert all(i["type"] == "to-do" for i in anytime["items"])


def test_board_cards_counts(things_db):
    board = {"include_projects": ["proj-book"], "include_areas": ["area-work"]}
    cards = {c["id"]: c for c in reads.board_cards(board)}
    assert cards["proj-book"]["open"] >= 0  # cached counts default to 0 in the fixture
    assert cards["area-work"]["kind"] == "area"


def test_card_projection_is_compact(things_db):
    (card,) = [reads._card(t) for t in reads.today() if t["uuid"] == "todo-today"]
    assert card["has_notes"] is True
    assert "notes" not in card
    assert card["tags"] == ["urgent"]
