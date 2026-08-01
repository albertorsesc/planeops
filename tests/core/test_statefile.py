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
