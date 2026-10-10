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
