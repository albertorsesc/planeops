import json

import yaml

from engine.cli import main
from engine.importers import discover_importers
from engine.importers.observed import ObservedImporter, propose_from_snapshot


def _snapshot(observed, host="testhost"):
    return json.dumps({"host": host, "observed": observed})


def test_proposes_one_entry_per_observed_item_with_the_adapter_domain():
    snap = _snapshot(
        [
            {"adapter": "pkg-brew", "native_id": "ripgrep", "facts": {}},
            {"adapter": "ollama", "native_id": "qwen3:7b", "facts": {}},
            {"adapter": "mcp", "native_id": "context7", "facts": {}},
        ]
    )
    by_id = {e["id"]: e for e in propose_from_snapshot(snap, None)}
    brew = by_id["pkg-brew/ripgrep"]
    assert brew["domain"] == "package"  # inferred from the adapter
    assert brew["lifecycle"] == "active" and brew["tolerance"] == "report"
    assert "verify" in brew["intent"]
    assert by_id["ollama/qwen3:7b"]["domain"] == "model"
    assert by_id["mcp/context7"]["domain"] == "mcp-server"


def test_skips_already_declared_entries(tmp_path):
    reg = tmp_path / "registry"
    reg.mkdir()
    (reg / "r.yaml").write_text(
        "entries:\n"
        "  - {id: pkg-brew/ripgrep, adapter: pkg-brew, domain: package, "
        "lifecycle: active, intent: i}\n"
    )
    snap = _snapshot(
        [
            {"adapter": "pkg-brew", "native_id": "ripgrep", "facts": {}},
            {"adapter": "pkg-brew", "native_id": "jq", "facts": {}},
        ]
    )
    ids = [e["id"] for e in propose_from_snapshot(snap, tmp_path)]
    assert ids == ["pkg-brew/jq"]  # ripgrep already declared -> not re-proposed


def test_dedupes_and_ignores_malformed_items():
    snap = _snapshot(
        [
            {"adapter": "ollama", "native_id": "a", "facts": {}},
            {"adapter": "ollama", "native_id": "a", "facts": {}},  # duplicate
            {"adapter": "ollama"},  # no native_id -> skip
            "not a dict",  # skip
        ]
    )
    assert [e["id"] for e in propose_from_snapshot(snap, None)] == ["ollama/a"]


def test_bad_or_empty_input_yields_no_proposals():
    assert propose_from_snapshot("{not json", None) == []
    assert propose_from_snapshot("[]", None) == []  # valid JSON, not an object
    assert propose_from_snapshot(_snapshot([]), None) == []  # no observed items
    # present-but-null / wrong-type `observed` must not raise (documented contract)
    assert (
        propose_from_snapshot(json.dumps({"host": "h", "observed": None}), None) == []
    )
    assert propose_from_snapshot(json.dumps({"host": "h", "observed": 5}), None) == []


def test_discovered_as_kind_observed():
    imp = discover_importers().get("observed")
    assert isinstance(imp, ObservedImporter)
    assert imp.kind == "observed"


def test_skips_a_declared_id_even_on_another_host(tmp_path):
    # ids are globally unique, so a declared id is skipped regardless of its host,
    # else the saved registry would fail load on a duplicate id.
    reg = tmp_path / "registry"
    reg.mkdir()
    (reg / "r.yaml").write_text(
        "entries:\n  - {id: pkg-brew/ripgrep, adapter: pkg-brew, domain: package, "
        "lifecycle: active, intent: i, hosts: [otherhost]}\n"
    )
    snap = _snapshot(
        [{"adapter": "pkg-brew", "native_id": "ripgrep", "facts": {}}], host="thishost"
    )
    assert propose_from_snapshot(snap, tmp_path) == []


def test_facts_and_version_never_appear_in_the_proposal():
    # the one security-relevant property: only aggregate id/domain/etc cross over,
    # never an observed item's facts (which other adapters may populate) or version.
    snap = _snapshot(
        [
            {
                "adapter": "ollama",
                "native_id": "m",
                "facts": {"path": "/p", "configured": True},
                "version": "1.2",
            }
        ]
    )
    proposal = propose_from_snapshot(snap, None)[0]
    assert set(proposal) == {
        "id", "adapter", "domain", "lifecycle", "tolerance", "intent",
    }  # fmt: skip


def test_proposals_are_grouped_by_adapter_type():
    snap = _snapshot(
        [
            {"adapter": "pkg-brew", "native_id": "z", "facts": {}},
            {"adapter": "mcp", "native_id": "a", "facts": {}},
            {"adapter": "pkg-brew", "native_id": "a", "facts": {}},
            {"adapter": "ollama", "native_id": "m", "facts": {}},
        ]
    )
    adapters = [e["adapter"] for e in propose_from_snapshot(snap, None)]
    assert adapters == sorted(adapters)  # contiguous by type, not a shuffled wall


def test_cli_adapter_filter_onboards_one_type_at_a_time(tmp_path, capsys):
    snap = tmp_path / "snap.json"
    snap.write_text(
        json.dumps(
            {
                "host": "h",
                "observed": [
                    {"adapter": "ollama", "native_id": "m1", "facts": {}},
                    {"adapter": "pkg-brew", "native_id": "ripgrep", "facts": {}},
                ],
            }
        )
    )
    (tmp_path / ".planeops").write_text("")  # marks tmp_path as the instance root
    code = main(
        [
            "--repo",
            str(tmp_path),
            "import",
            "observed",
            str(snap),
            "--adapter",
            "ollama",
        ]
    )
    assert code == 0
    doc = yaml.safe_load(capsys.readouterr().out)  # the note line is a YAML comment
    assert [e["id"] for e in doc["entries"]] == ["ollama/m1"]  # pkg-brew filtered out
