"""`plane init`: scaffold an instance and register it in the home config dir.

One command a fresh user (or the author, adopting) runs to establish the canonical
setup: a `.planeops` marker + `registry/` + a starter `instance.yaml` in the chosen
directory, and `~/.config/planeops/config.toml` pointing at it, so the installed
`plane` finds it from anywhere. Never clobbers existing files; the config pointer is
only repointed with `force`.
"""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path


def _starter_instance_yaml() -> str:
    """The commented reference instance.yaml, shipped as package data so an installed
    `plane` scaffolds the same fully-documented starter a repo checkout would."""
    return (files("planeops") / "instance.example.yaml").read_text()


def init_instance(
    instance_path: Path, config_dir: Path, *, force: bool = False
) -> list[str]:
    """Scaffold `instance_path` and point `config_dir/config.toml` at it. Returns the
    human-readable actions taken. Idempotent: existing files are kept, and the config
    pointer is repointed only with `force`."""
    actions: list[str] = []
    inst = instance_path.expanduser()
    inst.mkdir(parents=True, exist_ok=True)

    marker = inst / ".planeops"
    if not marker.exists():
        marker.write_text("")
        actions.append(f"created {marker}")

    reg = inst / "registry"
    if not reg.is_dir():
        reg.mkdir(parents=True)
        actions.append(f"created {reg}/")

    instance_yaml = inst / "instance.yaml"
    if not instance_yaml.exists():
        instance_yaml.write_text(_starter_instance_yaml())
        actions.append(f"wrote {instance_yaml}")

    config_dir = config_dir.expanduser()
    conf = config_dir / "config.toml"
    abs_inst = inst.resolve()
    if conf.is_file() and not force:
        actions.append(f"kept {conf} (use --force to repoint)")
    else:
        config_dir.mkdir(parents=True, exist_ok=True)
        # json.dumps yields a correctly-escaped TOML basic string for the path value.
        conf.write_text(
            f"# planeops: where your instance lives.\n"
            f"instance = {json.dumps(str(abs_inst))}\n"
        )
        actions.append(f"pointed {conf} -> {abs_inst}")
    return actions
