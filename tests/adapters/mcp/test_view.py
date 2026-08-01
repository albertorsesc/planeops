"""`plane mcp`: a pure read of the last snapshot into a cross-client MCP view.

The view answers the one question no single client's config can: every MCP server
and which clients each is wired into, plus the three call-outs the merged picture
makes visible (single-client, name drift, ungoverned).
"""

import json

from planeops.adapters.mcp.view import build_mcp_view, read_mcp_view, render_mcp_view


def _snapshot(servers, host="testhost", ts="2026-07-29T00:00:00"):
    """servers: {name: [client, ...]}. Includes a non-mcp fact the view must ignore."""
    observed = [
        {
            "adapter": "mcp",
            "native_id": name,
            "facts": {"sources": sorted(clients), "command": ""},
            "version": None,
        }
        for name, clients in servers.items()
    ]
    observed.append(
        {"adapter": "pkg-brew", "native_id": "ripgrep", "facts": {}, "version": None}
    )
    return {"host": host, "ts": ts, "observed": observed}


def test_maps_each_server_to_its_clients_ignoring_non_mcp_facts():
    snap = _snapshot(
        {"context7": ["claude-code"], "gitnexus": ["cursor", "claude-code"]}
    )
    view = build_mcp_view(snap, declared_ids={"mcp/context7", "mcp/gitnexus"})
    by_name = {s["name"]: s for s in view["servers"]}
    assert set(by_name) == {"context7", "gitnexus"}  # pkg-brew/ripgrep excluded
    assert by_name["gitnexus"]["clients"] == ["claude-code", "cursor"]  # sorted
    assert by_name["context7"]["id"] == "mcp/context7"


def test_servers_are_sorted_by_name():
    names = [
        s["name"]
        for s in build_mcp_view(_snapshot({"z": ["a"], "a": ["a"]}), set())["servers"]
    ]
    assert names == sorted(names)


def test_flags_single_client_servers_as_reuse_candidates():
    snap = _snapshot({"solo": ["claude-code"], "shared": ["claude-code", "cursor"]})
    view = build_mcp_view(snap, set())
    assert view["single_client"] == ["solo"]  # shared spans 2 clients -> not flagged


def test_flags_ungoverned_servers_observed_but_not_declared():
    snap = _snapshot({"context7": ["claude-code"], "tolaria": ["cursor"]})
    view = build_mcp_view(snap, declared_ids={"mcp/context7"})
    assert view["ungoverned"] == ["tolaria"]
    by_name = {s["name"]: s for s in view["servers"]}
    assert by_name["context7"]["governed"] is True
    assert by_name["tolaria"]["governed"] is False


def test_flags_name_drift_same_tool_under_different_names():
    # the documented real case: an "mcp-" prefixed name in one client, bare in another.
    snap = _snapshot(
        {
            "mcp-sequentialthinking-tools": ["claude-desktop"],
            "sequentialthinking-tools": ["claude-code"],
            "context7": ["claude-code"],
        }
    )
    view = build_mcp_view(snap, set())
    assert view["name_drift"] == [
        {"names": ["mcp-sequentialthinking-tools", "sequentialthinking-tools"]}
    ]  # context7 is alone -> not a drift group


def test_a_single_name_is_never_name_drift():
    assert (
        build_mcp_view(_snapshot({"context7": ["a", "b"]}), set())["name_drift"] == []
    )


def test_empty_or_non_mcp_snapshot_yields_an_empty_view():
    view = build_mcp_view({"host": "h", "ts": "t", "observed": []}, set())
    assert view["servers"] == [] and view["single_client"] == []
    assert view["ungoverned"] == [] and view["name_drift"] == []


def test_read_mcp_view_reads_the_snapshot_and_registry(tmp_path, fake_platform):
    reg = tmp_path / "registry"
    reg.mkdir()
    (reg / "r.yaml").write_text(
        "entries:\n  - {id: mcp/context7, adapter: mcp, domain: mcp-server, "
        "lifecycle: active, intent: i}\n"
    )
    d = tmp_path / "observed" / "testhost"
    d.mkdir(parents=True)
    (d / "snapshot.json").write_text(
        json.dumps(_snapshot({"context7": ["claude-code"], "tolaria": ["cursor"]}))
    )
    view = read_mcp_view(tmp_path, platform=fake_platform(tmp_path))
    assert view is not None
    assert view["ungoverned"] == ["tolaria"]  # context7 declared, tolaria not


def test_read_mcp_view_is_none_when_no_snapshot(tmp_path, fake_platform):
    assert read_mcp_view(tmp_path, platform=fake_platform(tmp_path)) is None


def test_read_mcp_view_is_none_on_a_torn_or_corrupt_snapshot(tmp_path, fake_platform):
    d = tmp_path / "observed" / "testhost"
    d.mkdir(parents=True)
    (d / "snapshot.json").write_text("{partial")  # invalid / half-written JSON
    assert read_mcp_view(tmp_path, platform=fake_platform(tmp_path)) is None


def test_render_lists_servers_their_clients_and_the_flags():
    view = build_mcp_view(
        _snapshot({"context7": ["claude-code"], "tolaria": ["cursor"]}),
        declared_ids={"mcp/context7"},
    )
    out = render_mcp_view(view)
    assert "context7" in out and "claude-code" in out
    assert "tolaria" in out and "cursor" in out
    assert "ungoverned" in out.lower()


def test_read_mcp_view_none_on_valid_json_that_is_not_an_object(
    tmp_path, fake_platform
):
    # A snapshot.json that is valid JSON but not an object reads as "no view", not a
    # crash on `snapshot.get(...)`.
    d = tmp_path / "observed" / "testhost"
    d.mkdir(parents=True)
    (d / "snapshot.json").write_text("null")
    assert read_mcp_view(tmp_path, platform=fake_platform(tmp_path)) is None


def test_wrapper_only_names_do_not_falsely_merge_into_one_drift_group():
    # "mcp" and "mcp-server" both strip to empty; the fallback keeps them distinct so
    # they don't collapse into a bogus name-drift group. (The real drift pair still
    # merges, covered above.)
    snap = _snapshot({"mcp": ["a"], "mcp-server": ["b"], "real-tool": ["c"]})
    assert build_mcp_view(snap, set())["name_drift"] == []
