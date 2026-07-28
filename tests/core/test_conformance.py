"""Shared adapter conformance suite (SPEC.md section 7).

Every adapter, present and future, must satisfy the same contract: it is an
`Adapter`, `observe` returns well-formed `Observed`, and (if it mutates) `plan`
is pure and well-formed. The coverage gates below fail if a new adapter is added
without wiring it in here, so conformance can't be silently skipped.

Hermetic by construction: each adapter is built with fake seams (an empty runner,
empty fixture dirs, no sources) so `observe` touches nothing on the real machine.
"""

from datetime import datetime

import pytest

from engine.adapters._run import RunResult
from engine.adapters.chezmoi import ChezmoiAdapter
from engine.adapters.launchd import LaunchdAdapter
from engine.adapters.manual import ManualAdapter
from engine.adapters.mcp import McpAdapter
from engine.adapters.ollama import OllamaAdapter
from engine.adapters.pkg_brew import PkgBrewAdapter
from engine.adapters.pkg_npm import PkgNpmAdapter
from engine.adapters.pkg_nvm import PkgNvmAdapter
from engine.adapters.pkg_uv import PkgUvAdapter
from engine.adapters.secrets import SecretsAdapter
from engine.core.contracts import Adapter, Change, Ctx, Observed, can_apply
from engine.core.discovery import discover_adapters
from engine.core.schema import entry_from_dict

CHANGE_KINDS = {"install", "configure", "remove", "patch"}


def _empty_run(cmd):
    return RunResult(0, "", "")


def _hermetic_adapters(tmp_path):
    """One instance per adapter, wired so observe reads nothing real."""
    empty = tmp_path / "empty"
    empty.mkdir(exist_ok=True)
    return {
        "manual": ManualAdapter(),
        "launchd": LaunchdAdapter(run=_empty_run, agents_dir=empty),
        "ollama": OllamaAdapter(run=_empty_run),
        "pkg-brew": PkgBrewAdapter(run=_empty_run),
        "pkg-uv": PkgUvAdapter(run=_empty_run),
        "pkg-npm": PkgNpmAdapter(run=_empty_run),
        "pkg-nvm": PkgNvmAdapter(nvm_dir=empty),
        "mcp": McpAdapter(sources=[]),
        "chezmoi": ChezmoiAdapter(run=_empty_run),
        "secrets": SecretsAdapter(),
    }


# One sample entry per MUTATING adapter, for the plan-purity checks.
_SAMPLE = {
    "launchd": ("service", "com.example.svc"),
    "ollama": ("model", "mistral:7b"),
    "pkg-brew": ("package", "ripgrep"),
    "pkg-uv": ("package", "ruff"),
    "pkg-npm": ("package", "typescript"),
    "chezmoi": ("config", "somefile"),
    "secrets": ("secret", "openrouter-api-key"),
}


def _ctx(platform, repo_root):
    return Ctx(
        platform=platform,
        host="testhost",
        now=datetime(2026, 7, 27),
        entries=(),
        repo_root=repo_root,
    )


# ---- structural: over every DISCOVERED adapter ---------------------------


@pytest.mark.parametrize("name, adapter", sorted(discover_adapters().items()))
def test_discovered_adapter_satisfies_contract(name, adapter):
    assert isinstance(adapter, Adapter)
    assert isinstance(adapter.name, str) and adapter.name
    assert adapter.name == name
    assert isinstance(adapter.domains, tuple)
    assert all(isinstance(d, str) for d in adapter.domains)


def test_every_discovered_adapter_is_covered_here(tmp_path):
    # A new adapter must be wired into _hermetic_adapters or this fails.
    assert set(discover_adapters()) == set(_hermetic_adapters(tmp_path))


def test_sample_entries_cover_every_mutating_adapter(tmp_path):
    mutating = {n for n, a in _hermetic_adapters(tmp_path).items() if can_apply(a)}
    assert set(_SAMPLE) == mutating


# ---- behavioral: hermetic ------------------------------------------------


def test_observe_returns_wellformed_observed(tmp_path, fake_platform):
    # A manual entry forces the manual adapter to emit an Observed, so the
    # shared-shape assertions below actually run rather than passing vacuously.
    manual_entry = entry_from_dict(
        {
            "id": "manual/thing",
            "adapter": "manual",
            "domain": "host",
            "lifecycle": "active",
            "intent": "conformance",
        }
    )
    ctx = Ctx(
        platform=fake_platform(tmp_path),
        host="testhost",
        now=datetime(2026, 7, 27),
        entries=(manual_entry,),
        repo_root=tmp_path,
    )
    checked = 0
    for name, adapter in _hermetic_adapters(tmp_path).items():
        result = adapter.observe(ctx)
        assert isinstance(result, list), name
        for obs in result:
            assert isinstance(obs, Observed)
            assert obs.adapter == name
            assert obs.key == f"{name}/{obs.native_id}"
            assert isinstance(obs.facts, dict)
            assert obs.version is None or isinstance(obs.version, str)
            checked += 1
    assert checked >= 1  # the manual entry guarantees at least one real Observed


def test_plan_is_pure_and_wellformed(tmp_path):
    adapters = _hermetic_adapters(tmp_path)
    for name, (domain, native) in _SAMPLE.items():
        adapter = adapters[name]
        entry = entry_from_dict(
            {
                "id": f"{name}/{native}",
                "adapter": name,
                "domain": domain,
                "lifecycle": "active",
                "intent": "conformance",
            }
        )
        first = adapter.plan(entry, None)
        second = adapter.plan(entry, None)
        assert first == second, f"{name}: plan is not deterministic"
        assert isinstance(first, list)
        for change in first:
            assert isinstance(change, Change)
            assert change.entry_id == entry.id
            assert change.kind in CHANGE_KINDS
            assert isinstance(change.action, dict)


def test_observe_only_adapters_do_not_expose_apply(tmp_path):
    adapters = _hermetic_adapters(tmp_path)
    for name in ("manual", "mcp", "pkg-nvm"):
        assert not can_apply(adapters[name])
