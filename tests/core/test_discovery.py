from engine.core.contracts import Adapter, can_apply
from engine.core.discovery import discover_adapters


def test_manual_adapter_found_by_package_scan():
    adapters = discover_adapters()
    assert "manual" in adapters
    assert isinstance(adapters["manual"], Adapter)


def test_manual_is_observe_only():
    adapters = discover_adapters()
    assert not can_apply(adapters["manual"])
