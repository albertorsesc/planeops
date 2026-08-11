"""Which documented sections an existing instance has not adopted.

A release can add an adapter, and an instance created before it never learns
that a new section exists: `plane init` writes the starter file once and then
keeps its hands off. This finds the difference and hands over the block to
paste, without ever editing the file, because instance.yaml is the operator's.
"""

from planeops.core.sections import documented_sections, missing_sections

EXAMPLE = """\
# Per-machine settings.

# --- alpha adapter: does the first thing ------------------------------------
# Some documentation for alpha.
# alpha:
#   roots:
#     - {label: one, path: ~/.one}

# --- beta: the second thing -------------------------------------------------
# Beta ships enabled by default.
beta:
  rules:
    - keyword: thing
"""


def test_documented_sections_are_found_commented_or_active():
    found = documented_sections(EXAMPLE)
    assert sorted(found) == ["alpha", "beta"]


def test_a_block_carries_its_own_documentation():
    # The point is that the pasted block explains itself, so the header
    # comment travels with the keys.
    block = documented_sections(EXAMPLE)["alpha"]
    assert block.startswith("# --- alpha adapter:")
    assert "Some documentation for alpha." in block
    assert "# alpha:" in block
    assert "beta" not in block  # blocks do not bleed into each other


def test_missing_is_what_the_instance_lacks():
    instance = "beta:\n  rules: []\n"
    assert [name for name, _ in missing_sections(instance, EXAMPLE)] == ["alpha"]


def test_nothing_missing_when_every_section_is_configured():
    instance = "alpha:\n  roots: []\nbeta:\n  rules: []\n"
    assert missing_sections(instance, EXAMPLE) == []


def test_a_commented_out_section_in_the_instance_still_counts_as_missing():
    # Commenting a section out is how you turn an adapter off, and an adapter
    # that is off is one you have not adopted.
    instance = "# alpha:\n#   roots: []\nbeta:\n  rules: []\n"
    assert [name for name, _ in missing_sections(instance, EXAMPLE)] == ["alpha"]


def test_an_unreadable_instance_reports_everything_rather_than_nothing():
    # A file we cannot parse must not read as "fully configured", which would
    # hide every section behind a syntax error.
    assert len(missing_sections("::: not yaml :::", EXAMPLE)) == 2


def test_it_reads_the_shipped_example_this_build_carries():
    # No argument: the example is package data, so an installed plane answers
    # for the adapters that build actually ships.
    found = documented_sections()
    assert {"mcp", "footprint", "harness", "importer", "secrets"} <= set(found)
    for name, block in found.items():
        assert block.strip(), name
        assert name in block, name
