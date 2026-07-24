from engine.core.contracts import Adapter
from engine.core.discovery import discover_adapters


def test_adapters_found_by_package_scan():
    adapters = discover_adapters()
    assert "manual" in adapters
    assert "launchd" in adapters
    for adapter in adapters.values():
        assert isinstance(adapter, Adapter)


def test_manual_is_observe_only():
    manual = discover_adapters()["manual"]
    assert not hasattr(manual, "execute")
    assert not hasattr(manual, "plan")
