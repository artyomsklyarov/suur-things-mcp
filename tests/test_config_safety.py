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
