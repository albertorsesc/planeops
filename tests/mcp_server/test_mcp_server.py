"""The `plane-mcp` entry point: base installs get a clear message, not a traceback."""

import builtins
import sys

import pytest

from planeops.mcp_server import main


def test_missing_mcp_extra_exits_with_install_hint(monkeypatch):
    # The base wheel ships the plane-mcp script; without the extra it must say
    # how to get the dependency, not traceback at import.
    real_import = builtins.__import__

    def no_mcp(name, *args, **kwargs):
        if name == "mcp" or name.startswith("mcp."):
            raise ModuleNotFoundError(f"No module named {name!r}", name=name)
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "planeops.mcp_server.server", raising=False)
    monkeypatch.setattr(builtins, "__import__", no_mcp)
    with pytest.raises(SystemExit, match=r"planeops\[mcp\]"):
        main()


def test_other_import_errors_still_surface(monkeypatch):
    # Only a missing `mcp` package gets the friendly exit; a genuinely broken
    # transitive import must not be swallowed into the same message.
    real_import = builtins.__import__

    def broken_dep(name, *args, **kwargs):
        if name == "mcp" or name.startswith("mcp."):
            raise ModuleNotFoundError("No module named 'other_dep'", name="other_dep")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "planeops.mcp_server.server", raising=False)
    monkeypatch.setattr(builtins, "__import__", broken_dep)
    with pytest.raises(ModuleNotFoundError, match="other_dep"):
        main()


def test_with_the_extra_installed_main_runs_the_server(monkeypatch):
    ran = []
    import planeops.mcp_server.server as server

    monkeypatch.setattr(server, "main", lambda: ran.append(True))
    main()
    assert ran == [True]
