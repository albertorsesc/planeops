"""The shared state-file contract: atomic writes, torn-safe JSON reads.

Every writer of durable per-host state uses `atomic_write`; every reader uses the
torn-safe readers, so a file killed mid-write, or hand-corrupted, reads as "nothing
yet" instead of crashing a later command.
"""

from planeops.core.statefile import atomic_write, read_host_json, read_json_file


def test_atomic_write_lands_content_and_leaves_no_tmp(tmp_path):
    p = tmp_path / "s.json"
    atomic_write(p, '{"a": 1}\n')
    assert p.read_text() == '{"a": 1}\n'
    assert not (tmp_path / "s.json.tmp").exists()  # temp sibling was renamed away


def test_atomic_write_overwrites_existing(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("old")
    atomic_write(p, "new")
    assert p.read_text() == "new"


def test_read_json_file_missing_is_none(tmp_path):
    assert read_json_file(tmp_path / "nope.json") is None


def test_read_json_file_torn_is_none(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{half-written")  # invalid / mid-write JSON
    assert read_json_file(p) is None


def test_read_json_file_valid_but_not_an_object_is_none(tmp_path):
    # valid JSON that is a list or scalar reads as None, so downstream `.get` is safe.
    for text in ("[]", "null", "5", '"str"'):
        p = tmp_path / "s.json"
        p.write_text(text)
        assert read_json_file(p) is None, text


def test_read_json_file_object_returns_the_dict(tmp_path):
    p = tmp_path / "s.json"
    p.write_text('{"a": 1}')
    assert read_json_file(p) == {"a": 1}


def test_read_host_json_builds_the_host_path(tmp_path, fake_platform):
    d = tmp_path / "observed" / "testhost"
    d.mkdir(parents=True)
    (d / "snapshot.json").write_text('{"host": "testhost"}')
    plat = fake_platform(tmp_path)
    assert read_host_json(tmp_path, "snapshot.json", platform=plat) == {
        "host": "testhost"
    }
    assert read_host_json(tmp_path, "missing.json", platform=plat) is None


# ---- atomic_write_foreign: files planeops does not own ----


def test_foreign_write_goes_through_a_symlink(tmp_path):
    from planeops.core.statefile import atomic_write_foreign

    real = tmp_path / "dotfiles" / "config.json"
    real.parent.mkdir()
    real.write_text("{}")
    link = tmp_path / "config.json"
    link.symlink_to(real)
    atomic_write_foreign(link, '{"a": 1}')
    assert link.is_symlink()  # the link survived
    assert real.read_text() == '{"a": 1}'  # the target got the bytes


def test_foreign_write_preserves_a_0600_mode(tmp_path):
    import os

    from planeops.core.statefile import atomic_write_foreign

    p = tmp_path / "secretish.json"
    p.write_text("{}")
    os.chmod(p, 0o600)
    atomic_write_foreign(p, '{"b": 2}')
    assert p.stat().st_mode & 0o777 == 0o600


def test_foreign_write_leaves_no_temp_on_failure(tmp_path, monkeypatch):
    import os

    import pytest

    from planeops.core import statefile

    p = tmp_path / "cfg.json"
    p.write_text("{}")

    def boom(src, dst):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        statefile.atomic_write_foreign(p, "{}")
    leftovers = [q for q in tmp_path.iterdir() if q.name != "cfg.json"]
    assert leftovers == []
