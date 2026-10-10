"""Config and attachment safety regressions using disposable storage only."""

import pytest

from suur_things_mcp import config


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("SUUR_THINGS_CONFIG", str(tmp_path / "board.json"))
    return tmp_path


def test_upload_rejects_symlink_to_prefix_sibling(store):
    outside = store / "attachments-other"
    outside.mkdir()
    config._attach_dir().mkdir()
    (config._attach_dir() / "task").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="attachment path"):
        config.save_attachment("task", b"image", "image/png", "photo.png")
    assert list(outside.iterdir()) == []
    assert config.attachments() == {}


def test_detach_preserves_file_and_metadata_outside_attachment_root(store):
    meta = config.save_attachment("task", b"image", "image/png", "photo.png")
    original = config.attachment_path("task", meta)
    outside = store / "attachments-other"
    outside.mkdir()
    sentinel = outside / original.name
    sentinel.write_bytes(b"user data")
    original.unlink()
    original.parent.rmdir()
    original.parent.symlink_to(outside, target_is_directory=True)
    assert config.remove_attachment("task", meta["id"]) is False
    assert sentinel.read_bytes() == b"user data"
    assert config.attachment_meta("task", meta["id"]) == meta


@pytest.mark.parametrize("item_id", ["../outside", "/tmp/outside", "task\n"])
def test_attachment_path_rejects_unsafe_stored_item_id(store, item_id):
    with pytest.raises(ValueError):
        config.attachment_path(item_id, {"id": "image", "mime": "image/png"})


@pytest.mark.parametrize("payload", [b"[]", b"null", b'"text"', b"23", b"\xff", b"{bad json"])
def test_unusable_config_is_preserved_and_recovers(store, payload):
    path = store / "board.json"
    path.write_bytes(payload)
    assert config.load()["boards"]
    backups = list(store.glob("board.json.corrupt-*"))
    assert len(backups) == 1 and backups[0].read_bytes() == payload
    assert config.load()["boards"]
    assert len(list(store.glob("board.json.corrupt-*"))) == 1
    config.merge({"prefs": {"editor": "code"}})
    assert backups[0].read_bytes() == payload
    assert config.prefs() == {"editor": "code"}


def test_recovery_does_not_overwrite_distinct_corrupt_configs(store):
    path = store / "board.json"
    for payload in [b"{broken-one", b"{broken-two"]:
        path.write_bytes(payload)
        config.load()
    assert {p.read_bytes() for p in store.glob("board.json.corrupt-*")} == {b"{broken-one", b"{broken-two"}


def test_unreadable_config_does_not_silently_reset(store, monkeypatch):
    config.save({"prefs": {"editor": "user-editor"}})
    original = (store / "board.json").read_bytes()

    def denied(*args, **kwargs):
        raise PermissionError("not readable")

    monkeypatch.setattr(type(store), "read_bytes", denied)
    with pytest.raises(PermissionError):
        config.merge({"priority": {"x": "do"}})
    monkeypatch.undo()
    assert (store / "board.json").read_bytes() == original


@pytest.mark.parametrize("repos", [42, True, {"repo": "bad"}, "bad"])
def test_junk_repo_lists_are_ignored_without_crashing(store, repos):
    cfg = config.save({"links": {"x": {"repos": repos}}, "prefs": {"editor": "code"}})
    assert cfg["links"] == {}
    assert cfg["prefs"] == {"editor": "code"}


def test_concurrent_uploads_obey_cap_without_losing_images(store, monkeypatch):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setattr(config, "MAX_ATTACH_PER_ITEM", 2)
    original_load = config.load

    def slow_load():
        result = original_load()
        time.sleep(0.02)  # simulate overlapping disk reads from multiple clients
        return result

    monkeypatch.setattr(config, "load", slow_load)
    start = threading.Barrier(8)

    def upload(i):
        start.wait(timeout=5)
        try:
            return config.save_attachment("task", bytes([i]), "image/png", f"{i}.png")
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(upload, range(8)))
    accepted = [meta for meta in results if meta]
    assert len(accepted) == 2
    assert {a["id"] for a in config.attachments()["task"]} == {a["id"] for a in accepted}
    assert len(list((config._attach_dir() / "task").iterdir())) == 2


def test_concurrent_direct_saves_have_distinct_atomic_temp_files(store, monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    ready = threading.Barrier(2)
    replace = config.os.replace

    def together(source, destination):
        ready.wait(timeout=5)
        replace(source, destination)

    monkeypatch.setattr(config.os, "replace", together)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda n: config.save({"prefs": {"editor": str(n)}}), range(2)))
    assert config.prefs()["editor"] in {"0", "1"}
    assert not list(store.glob("board.json.tmp-*"))


@pytest.mark.parametrize("agent", ["claude", "codex"])
def test_organizer_preferences_survive_unrelated_saves(tmp_path, monkeypatch, agent):
    monkeypatch.setenv("SUUR_THINGS_CONFIG", str(tmp_path / "board.json"))
    saved = config.save({"prefs": {"agent": agent, "agent_model": "  custom-model  ", "editor": "cursor"}})
    assert saved["prefs"]["agent"] == agent
    assert saved["prefs"]["agent_model"] == "custom-model"
    config.merge({"priority": {"task": "do"}})
    assert config.prefs() == {"agent": agent, "agent_model": "custom-model", "editor": "cursor"}


@pytest.mark.parametrize(
    "prefs",
    [
        {"agent": "unsupported", "agent_model": []},
        {"agent": ["codex"], "agent_model": {}},
        {"agent": 42, "agent_model": 42},
        {"agent": None, "agent_model": "  "},
    ],
)
def test_invalid_organizer_preferences_are_ignored(tmp_path, monkeypatch, prefs):
    monkeypatch.setenv("SUUR_THINGS_CONFIG", str(tmp_path / "board.json"))
    assert config.save({"prefs": prefs})["prefs"] == {}
