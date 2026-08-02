from planeops.core.contracts import Adapter
from planeops.core.discovery import discover_adapters


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


def test_an_implementation_name_with_bad_charset_is_rejected():
    # Names feed `<adapter>/<native_id>` keys (split at the FIRST slash) and
    # unmanaged-glob matching; a slash or space in a name corrupts both. The
    # grammar is enforced at the seam, before any name can ship.

    from planeops.core.discovery import validate_seam_name

    for bad in ("has/slash", "Has Upper", "spa ce", ""):
        try:
            validate_seam_name(bad, context="test")
        except (TypeError, ValueError):
            continue
        raise AssertionError(f"{bad!r} was accepted")
    validate_seam_name("pkg-brew", context="test")  # every in-tree name passes
    validate_seam_name("pkg_uv2.x", context="test")
