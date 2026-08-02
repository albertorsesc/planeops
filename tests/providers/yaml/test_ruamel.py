"""The ruamel leaf satisfies the port surface exactly (a provider swap must
only need a sibling module exposing these same names)."""

from planeops.providers import yaml as port
from planeops.providers.yaml import ruamel


def test_leaf_exposes_the_full_port_surface():
    for name in port.__all__:
        assert hasattr(ruamel, name), f"provider missing port name {name!r}"
