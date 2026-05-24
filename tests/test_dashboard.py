"""Dashboard tests.

The `/` route is static and runs anywhere. The data routes need a readable
Things database, so they skip gracefully when Things isn't present (CI / Linux).
"""

import pytest
from starlette.testclient import TestClient

from suur_things_mcp import reads
from suur_things_mcp.dashboard import _pick_port, create_app

client = TestClient(create_app())


def _things_available() -> bool:
    try:
        reads.board()
        return True
    except Exception:
        return False


def test_index_route_is_static():
    r = client.get("/")
    assert r.status_code == 200
    assert "Things Board" in r.text


def test_pick_port_returns_free_port():
    port = _pick_port()
    assert isinstance(port, int) and 1 <= port <= 65535


def test_state_endpoint_never_500s():
    # Even with no Things DB, the endpoint returns a JSON envelope, not a 500.
    r = client.get("/api/state")
    assert r.status_code == 200
    body = r.json()
    assert "ok" in body and "board" in body


@pytest.mark.skipif(not _things_available(), reason="Things database not available")
def test_state_shape_with_things():
    body = client.get("/api/state").json()
    assert body["ok"] is True
    for col in ("inbox", "today", "upcoming", "anytime", "someday"):
        assert col in body["board"]


@pytest.mark.skipif(not _things_available(), reason="Things database not available")
def test_overview_shape_with_things():
    ov = reads.overview(recent_completed=5)
    assert set(ov) == {
        "counts",
        "today",
        "overdue",
        "projects_without_next_action",
        "recent_completed",
    }
    assert "today" in ov["counts"]
