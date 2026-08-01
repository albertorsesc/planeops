"""Integration: the chezmoi adapter against the REAL chezmoi binary.

Unit tests fake the runner; this proves the actual `chezmoi managed`/`status`/
`apply` invocations work, the exact case that caught a real bug (relative path +
missing --force). Skipped when chezmoi is absent; CI installs it.
"""

import shutil
import subprocess
from datetime import datetime

import pytest

from planeops.adapters.chezmoi import ChezmoiAdapter
from planeops.core.contracts import Ctx
from planeops.core.schema import entry_from_dict

pytestmark = pytest.mark.skipif(
    shutil.which("chezmoi") is None, reason="requires the real chezmoi binary"
)


class _Platform:
    name = "test"

    def __init__(self, home):
        self._home = home

    def hostname(self) -> str:
        return "h"

    def home(self):
        return self._home


def test_observe_flags_drift_and_apply_reproduces(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))  # isolate chezmoi's source under the tmp home

    rc = home / ".rehearsalrc"
    rc.write_text("REPRODUCED\n")
    subprocess.run(["chezmoi", "init"], check=True, capture_output=True)
    subprocess.run(["chezmoi", "add", str(rc)], check=True, capture_output=True)
    rc.write_text("DRIFTED\n")  # target now differs from source

    ctx = Ctx(platform=_Platform(home), host="h", now=datetime(2026, 7, 28))
    adapter = ChezmoiAdapter()  # real default_run

    observed = {o.native_id: o for o in adapter.observe(ctx)}
    assert observed[".rehearsalrc"].facts["drifted"] is True  # real `chezmoi status`

    entry = entry_from_dict(
        {
            "id": "chezmoi/.rehearsalrc",
            "adapter": "chezmoi",
            "domain": "config",
            "lifecycle": "active",
            "intent": "i",
        }
    )
    [change] = adapter.plan(entry, observed[".rehearsalrc"], ctx)
    res = adapter.execute(change, ctx)  # real `chezmoi apply --force <abs>`

    assert res.ok, res.detail
    assert rc.read_text() == "REPRODUCED\n"  # drift reproduced from source
