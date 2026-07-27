from datetime import datetime

from engine.adapters.pkg_nvm import ADAPTER, PkgNvmAdapter
from engine.core.contracts import Ctx, can_apply


def _ctx(platform):
    return Ctx(platform=platform, host="testhost", now=datetime(2026, 7, 27))


def _make_node_versions(root, versions):
    d = root / ".nvm" / "versions" / "node"
    for v in versions:
        (d / v).mkdir(parents=True, exist_ok=True)
    return d


def test_observe_reports_installed_node_versions(tmp_path, fake_platform):
    _make_node_versions(tmp_path, ["v24.14.1", "v20.11.0"])
    out = {
        o.native_id: o for o in PkgNvmAdapter().observe(_ctx(fake_platform(tmp_path)))
    }
    assert set(out) == {"24.14.1", "20.11.0"}
    assert out["24.14.1"].version == "24.14.1"
    assert out["24.14.1"].key == "pkg-nvm/24.14.1"


def test_missing_nvm_dir_is_empty_not_error(tmp_path, fake_platform):
    assert PkgNvmAdapter().observe(_ctx(fake_platform(tmp_path))) == []


def test_nvm_dir_override(tmp_path):
    d = tmp_path / "custom" / "node"
    (d / "v22.0.0").mkdir(parents=True)
    out = PkgNvmAdapter(nvm_dir=d).observe(_ctx(None))
    assert [o.native_id for o in out] == ["22.0.0"]


def test_pkg_nvm_is_observe_only():
    # nvm is a shell function, not a binary; there is no clean execute seam.
    assert not can_apply(ADAPTER)
