"""The mcp write side: every guard the design review demanded, exercised.

The fixture config imitates a real client file: servers plus unrelated
sections, non-ASCII content, and an env block whose sentinel value must never
appear anywhere but the file itself and the backup.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from planeops.adapters.mcp import McpAdapter, McpSource
from planeops.adapters.mcp import write as w
from planeops.core.contracts import Ctx
from planeops.core.schema import entry_from_dict

SENTINEL = "sk-SENTINEL-env-value-陽"


def _config(servers: dict) -> str:
    doc = {
        "projects": {"/x": {"history": ["opened once"]}},
        "mcpServers": servers,
        "trailer": "non-ascii: café",
    }
    return json.dumps(doc, indent=2, ensure_ascii=False)


def _machine(tmp_path, servers=None):
    servers = servers if servers is not None else {
        "doomed": {"command": "npx", "env": {"KEY": SENTINEL}},
        "kept": {"command": "uvx"},
    }  # fmt: skip
    cfg = tmp_path / "home" / ".claude.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(_config(servers), encoding="utf-8")
    inst = tmp_path / "inst"
    (inst / "registry").mkdir(parents=True, exist_ok=True)
    (inst / ".planeops").write_text("")
    (inst / "instance.yaml").write_text(
        "mcp:\n  manage: true\n  sources:\n"
        f"    - {{label: claude-code, path: {cfg}, format: json, key: mcpServers}}\n"
    )
    return cfg, inst


def _entry(name="doomed", lifecycle="retired"):
    return entry_from_dict(
        {"id": f"mcp/{name}", "adapter": "mcp", "domain": "mcp-server",
         "lifecycle": lifecycle, "intent": "i"}
    )  # fmt: skip


class _Plat:
    name = "fake"

    def __init__(self, home: Path):
        self._home = home

    def hostname(self):
        return "h"

    def home(self):
        return self._home


def _ctx(tmp_path, inst):
    return Ctx(
        platform=_Plat(tmp_path / "home"),
        host="h",
        now=datetime(2026, 8, 8),
        entries=(),
        repo_root=inst,
    )


def _observe_facts(cfg, inst, tmp_path):
    adapter = McpAdapter()
    out = {o.native_id: o for o in adapter.observe(_ctx(tmp_path, inst))}
    return adapter, out


def _plan(tmp_path, monkeypatch, entry=None):
    cfg, inst = _machine(tmp_path)
    monkeypatch.setattr(w, "BACKUP_DIR", tmp_path / "backups")
    adapter, out = _observe_facts(cfg, inst, tmp_path)
    entry = entry or _entry()
    changes = adapter.plan(entry, out.get("doomed"), _ctx(tmp_path, inst))
    return cfg, inst, adapter, changes


# ---- plan -----------------------------------------------------------------


def test_plan_targets_the_wired_client_with_digests(tmp_path, monkeypatch):
    cfg, inst, adapter, changes = _plan(tmp_path, monkeypatch)
    assert len(changes) == 1
    c = changes[0]
    assert c.entry_id == "mcp/doomed" and c.kind == "remove"
    [target] = c.action["targets"]
    assert target["label"] == "claude-code" and target["path"] == str(cfg)
    assert len(target["sha_file"]) == 64 and len(target["sha_block"]) == 64


def test_plan_diff_names_client_and_path_but_never_env(tmp_path, monkeypatch):
    cfg, inst, adapter, changes = _plan(tmp_path, monkeypatch)
    diff = changes[0].diff
    assert "claude-code" in diff and str(cfg) in diff
    assert SENTINEL not in diff and "env" not in diff
    assert SENTINEL not in json.dumps(changes[0].action)


def test_plan_requires_the_manage_opt_in(tmp_path, monkeypatch):
    cfg, inst = _machine(tmp_path)
    (inst / "instance.yaml").write_text(
        "mcp:\n  sources:\n"
        f"    - {{label: claude-code, path: {cfg}, format: json, key: mcpServers}}\n"
    )
    adapter, out = _observe_facts(cfg, inst, tmp_path)
    assert adapter.plan(_entry(), out["doomed"], _ctx(tmp_path, inst)) == []


def test_plan_only_absent_lifecycles(tmp_path, monkeypatch):
    cfg, inst = _machine(tmp_path)
    adapter, out = _observe_facts(cfg, inst, tmp_path)
    for lc in ("active", "parked"):
        assert (
            adapter.plan(_entry(lifecycle=lc), out["doomed"], _ctx(tmp_path, inst))
            == []
        )


def test_plan_skips_scoped_wirings_and_names_them(tmp_path, monkeypatch):
    entry = _entry()
    facts = {
        "wirings": [
            {"client": "claude-code", "scope": "repo:~/x"},
        ],
        "sources": ["claude-code repo:~/x"],
    }
    cfg, inst = _machine(tmp_path)
    sources = [McpSource("claude-code", str(cfg), "json", "mcpServers")]
    assert w.plan_unwire(entry, facts, _ctx(tmp_path, inst), sources) == []


def test_plan_without_wirings_fact_is_a_noop(tmp_path, monkeypatch):
    # A pre-upgrade snapshot has no structured fact: never guess from labels.
    cfg, inst = _machine(tmp_path)
    sources = [McpSource("claude-code", str(cfg), "json", "mcpServers")]
    facts = {"sources": ["claude-code"]}
    assert w.plan_unwire(_entry(), facts, _ctx(tmp_path, inst), sources) == []


# ---- execute --------------------------------------------------------------


def test_execute_removes_the_block_and_preserves_every_other_byte(
    tmp_path, monkeypatch
):
    cfg, inst, adapter, changes = _plan(tmp_path, monkeypatch)
    before = cfg.read_text(encoding="utf-8")
    res = adapter.execute(changes[0], _ctx(tmp_path, inst))
    assert res.ok, res.detail
    after = cfg.read_text(encoding="utf-8")
    assert '"doomed"' not in after and SENTINEL not in after
    # the untouched remainder is byte-identical: same serialization, block gone
    expected = json.loads(before)
    del expected["mcpServers"]["doomed"]
    assert after == json.dumps(expected, indent=2, ensure_ascii=False)
    assert "restarted" in res.detail  # the running-client caveat is stated


def test_execute_refuses_when_the_file_changed_since_the_preview(tmp_path, monkeypatch):
    cfg, inst, adapter, changes = _plan(tmp_path, monkeypatch)
    doc = json.loads(cfg.read_text())
    doc["projects"]["/y"] = {}
    cfg.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    before = cfg.read_text(encoding="utf-8")
    res = adapter.execute(changes[0], _ctx(tmp_path, inst))
    assert not res.ok and "changed since the preview" in res.detail
    assert cfg.read_text(encoding="utf-8") == before  # untouched


def test_execute_refuses_a_reformatted_file(tmp_path, monkeypatch):
    cfg, inst, adapter, changes = _plan(tmp_path, monkeypatch)
    doc = json.loads(cfg.read_text())
    cfg.write_text(json.dumps(doc, indent=4), encoding="utf-8")
    res = adapter.execute(changes[0], _ctx(tmp_path, inst))
    assert not res.ok
    assert cfg.read_text(encoding="utf-8") == json.dumps(doc, indent=4)


def test_execute_writes_a_backup_with_the_block(tmp_path, monkeypatch):
    cfg, inst, adapter, changes = _plan(tmp_path, monkeypatch)
    res = adapter.execute(changes[0], _ctx(tmp_path, inst))
    assert res.ok
    [backup] = list((tmp_path / "backups").iterdir())
    record = json.loads(backup.read_text(encoding="utf-8"))
    assert record["server"] == "doomed" and record["block"]["env"]["KEY"] == SENTINEL
    assert backup.stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "backups").stat().st_mode & 0o777 == 0o700


def test_result_detail_never_carries_env(tmp_path, monkeypatch):
    cfg, inst, adapter, changes = _plan(tmp_path, monkeypatch)
    res = adapter.execute(changes[0], _ctx(tmp_path, inst))
    assert SENTINEL not in res.detail


def test_two_clients_one_change_and_a_partial_refusal_names_the_written(
    tmp_path, monkeypatch
):
    # One server wired in two clients is ONE decision with two targets. When
    # the second file fails its guard mid-execute, the result must own the
    # half already written, not report a clean failure.
    servers = {"doomed": {"command": "npx", "env": {"KEY": SENTINEL}}}
    cfg1 = tmp_path / "home" / ".claude.json"
    cfg1.parent.mkdir(parents=True, exist_ok=True)
    cfg1.write_text(_config(servers), encoding="utf-8")
    cfg2 = tmp_path / "home" / "desktop.json"
    cfg2.write_text(
        json.dumps({"mcpServers": dict(servers)}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    inst = tmp_path / "inst"
    (inst / "registry").mkdir(parents=True, exist_ok=True)
    (inst / ".planeops").write_text("")
    (inst / "instance.yaml").write_text(
        "mcp:\n  manage: true\n  sources:\n"
        f"    - {{label: claude-code, path: {cfg1}, format: json, key: mcpServers}}\n"
        f"    - {{label: claude-desktop, path: {cfg2}, format: json, key: mcpServers}}\n"
    )
    monkeypatch.setattr(w, "BACKUP_DIR", tmp_path / "backups")
    adapter, out = _observe_facts(cfg1, inst, tmp_path)
    assert {w_["client"] for w_ in out["doomed"].facts["wirings"]} == {
        "claude-code",
        "claude-desktop",
    }
    changes = adapter.plan(_entry(), out["doomed"], _ctx(tmp_path, inst))
    assert len(changes) == 1 and len(changes[0].action["targets"]) == 2

    doc = json.loads(cfg2.read_text())
    doc["extra"] = 1
    cfg2.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    res = adapter.execute(changes[0], _ctx(tmp_path, inst))
    assert not res.ok
    assert res.detail.startswith("wrote claude-code")
    assert "then" in res.detail and "changed since the preview" in res.detail
    assert '"doomed"' not in cfg1.read_text(encoding="utf-8")  # first write landed
    assert '"doomed"' in cfg2.read_text(encoding="utf-8")  # second file untouched


def test_a_doctored_block_digest_refuses_even_when_the_file_matches(
    tmp_path, monkeypatch
):
    # sha_file passing implies the block is unchanged today; the block digest
    # still guards a future caller that builds actions some other way.
    cfg, inst, adapter, changes = _plan(tmp_path, monkeypatch)
    changes[0].action["targets"][0]["sha_block"] = "0" * 64
    res = adapter.execute(changes[0], _ctx(tmp_path, inst))
    assert not res.ok and "changed since the preview" in res.detail
    assert '"doomed"' in cfg.read_text(encoding="utf-8")


def test_a_hostile_server_name_still_backs_up(tmp_path, monkeypatch):
    # A name with path separators must not steer the backup outside its dir.
    servers = {"we/ird:陽": {"command": "npx", "env": {"KEY": SENTINEL}}}
    cfg, inst = _machine(tmp_path, servers=servers)
    monkeypatch.setattr(w, "BACKUP_DIR", tmp_path / "backups")
    adapter, out = _observe_facts(cfg, inst, tmp_path)
    entry = _entry(name="we/ird:陽")
    changes = adapter.plan(entry, out["we/ird:陽"], _ctx(tmp_path, inst))
    res = adapter.execute(changes[0], _ctx(tmp_path, inst))
    assert res.ok, res.detail
    [backup] = list((tmp_path / "backups").iterdir())
    assert backup.parent == tmp_path / "backups"
    record = json.loads(backup.read_text(encoding="utf-8"))
    assert record["server"] == "we/ird:陽"


# ---- strict reader edges --------------------------------------------------


def test_strict_reader_refuses_duplicate_keys(tmp_path):
    p = tmp_path / "dup.json"
    p.write_text('{\n  "a": 1,\n  "a": 2\n}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        w._read_strict(p)


def test_strict_reader_refuses_a_non_object(tmp_path):
    p = tmp_path / "arr.json"
    p.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="not a JSON object"):
        w._read_strict(p)


def test_strict_reader_refuses_a_relative_path():
    with pytest.raises(ValueError, match="absolute"):
        w._read_strict(Path("relative.json"))


def test_strict_reader_refuses_an_absent_file(tmp_path):
    with pytest.raises(ValueError, match="observe"):
        w._read_strict(tmp_path / "gone.json")
