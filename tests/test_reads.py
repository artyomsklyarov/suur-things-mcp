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


# --- age signals + staleness cohorts ---------------------------------------

def test_card_carries_age_signals(things_db):
    card = reads._card(reads.get("todo-today"))
    assert card["age_days"] == 0 and card["idle_days"] == 0
    # get_item still has the raw stamps; the card keeps only the cheap ints.
    assert "created" not in card and "modified" not in card


def test_days_since_tolerates_junk():
    assert reads._days_since(None) is None
    assert reads._days_since("") is None
    assert reads._days_since("not a date") is None
    assert reads._days_since("2026-08-28 10:11:58") >= 0


def _where(result, uuid):
    """Which cohort a uuid landed in, or None."""
    for name, cohort in result["cohorts"].items():
        if any(i["uuid"] == uuid for i in cohort["items"]):
            return name
    return None


def test_stale_cohort_assignment(stale_db):
    r = reads.stale_cohorts()
    assert _where(r, "stale-inbox") == "inbox_stale"
    assert _where(r, "stale-untouched") == "never_touched"
    assert _where(r, "stale-deferred") == "deferred"
    assert _where(r, "stale-loose") == "loose_stale"
    # Old + idle but inside a project: falls through to the per-project clusters.
    assert _where(r, "stale-clustered") is None
    assert any(c["project_title"] == "Write a book" and c["stale_count"] >= 1
               for c in r["clusters"])


def test_stale_cohorts_are_disjoint(stale_db):
    r = reads.stale_cohorts()
    seen = [i["uuid"] for c in r["cohorts"].values() for i in c["items"]]
    assert len(seen) == len(set(seen)), "an item appeared in two review queues"


def test_stale_deferred_reports_lateness(stale_db):
    item = next(i for i in reads.stale_cohorts()["cohorts"]["deferred"]["items"]
                if i["uuid"] == "stale-deferred")
    assert item["days_late"] == 30
    assert item["scheduled"] < __import__("datetime").date.today().isoformat()


def test_stale_dead_projects(stale_db):
    dead = {p["title"] for p in reads.stale_cohorts()["dead_projects"]}
    assert "Stalled project" in dead      # open project, no open to-dos
    assert "Write a book" not in dead     # still has open work


def test_stale_thresholds_are_honoured(stale_db):
    # stale-untouched is 500 days old; raise the bar past it and it drops out.
    r = reads.stale_cohorts(never_touched_days=600)
    assert _where(r, "stale-untouched") != "never_touched"
    assert r["thresholds"]["never_touched_days"] == 600


def test_stale_histogram_covers_every_open_todo(stale_db):
    r = reads.stale_cohorts()
    assert sum(r["age_histogram"].values()) == r["counts"]["open_todos"]
    assert r["age_histogram"]["> 1 year"] >= 1   # stale-untouched at 500d


def test_stale_limit_caps_items_but_not_total(stale_db):
    r = reads.stale_cohorts(limit=1)
    for cohort in r["cohorts"].values():
        assert len(cohort["items"]) <= 1
        assert cohort["total"] >= len(cohort["items"])
