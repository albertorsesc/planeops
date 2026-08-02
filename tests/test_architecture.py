"""Architecture fitness tests: the layering and organization rules, enforced by
the build instead of by memory.

Three properties the 2026-07 audit verified by hand become permanent here:
1. The core layer imports no extension package (adapters/importers/schedulers/
   cli/mcp_server); the one sanctioned edge is discovery's package scan.
2. The core layer names no vendor or OS tool in code: everything variable
   resolves through contracts and discovery, so a grep for "brew" in core
   staying empty is a build guarantee, not a habit.
3. Every logic-bearing engine module has its mirror test file, per the layout
   rule in CONTRIBUTING.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The core layer: modules that must know only contracts + resolution machinery.
# planeops/secrets/__init__.py (the contracts + redaction gate) and resolve.py
# (store discovery) belong here too: swapping a secrets store must never touch
# them, so they may not import a concrete store.
CORE_LAYER = [
    *sorted((ROOT / "planeops" / "core").glob("*.py")),
    ROOT / "planeops" / "_run.py",
    ROOT / "planeops" / "config.py",
    ROOT / "planeops" / "secrets" / "__init__.py",
    ROOT / "planeops" / "secrets" / "resolve.py",
]

EXTENSION_PACKAGES = (
    "planeops.adapters",
    "planeops.importers",
    "planeops.schedulers",
    "planeops.secrets.stores",
    "planeops.cli",
    "planeops.mcp_server",
)

# The sanctioned composition edges: each discovery scans its own namespace.
IMPORT_ALLOWLIST = {
    ("planeops/core/discovery.py", "planeops.adapters"),
    ("planeops/secrets/resolve.py", "planeops.secrets.stores"),
}

# Vendor/tool names that must never appear in core CODE (identifiers or
# non-docstring strings). Comments and docstrings may mention them as examples.
VENDOR_TOKENS = (
    "brew",
    "npm",
    "nvm",
    "ollama",
    "launchctl",
    "launchd",
    "systemctl",
    "systemd",
    "chezmoi",
    "sops",
)


def _imports(tree: ast.AST) -> list[str]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append(node.module)
    return out


def test_core_imports_no_extension_package():
    violations = []
    for path in CORE_LAYER:
        rel = str(path.relative_to(ROOT))
        tree = ast.parse(path.read_text())
        for mod in _imports(tree):
            for ext in EXTENSION_PACKAGES:
                hits = mod == ext or mod.startswith(ext + ".")
                if hits and (rel, ext) not in IMPORT_ALLOWLIST:
                    violations.append(f"{rel} imports {mod}")
    assert not violations, "core layer grew an extension import:\n" + "\n".join(
        violations
    )


def _code_strings_and_names(tree: ast.Module) -> list[str]:
    """Identifiers and string constants, excluding docstrings (a docstring may
    say 'e.g. launchd'; code must not)."""
    docstrings = set()
    doc_owners = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    for node in ast.walk(tree):
        if (
            isinstance(node, doc_owners)
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            docstrings.add(id(node.body[0].value))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.append(node.id)
        elif isinstance(node, ast.Attribute):
            out.append(node.attr)
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            out.append(node.value)
    return out


def test_core_code_names_no_vendor_or_os_tool():
    violations = []
    for path in CORE_LAYER:
        rel = str(path.relative_to(ROOT))
        tree = ast.parse(path.read_text())
        for text in _code_strings_and_names(tree):
            lowered = text.lower()
            for token in VENDOR_TOKENS:
                if token in lowered:
                    violations.append(f"{rel}: {text!r} contains {token!r}")
    assert not violations, "core layer learned a vendor name:\n" + "\n".join(violations)


def _has_logic(path: Path) -> bool:
    tree = ast.parse(path.read_text())
    return any(
        not isinstance(n, (ast.Expr, ast.ImportFrom, ast.Import)) for n in tree.body
    )


def test_every_engine_module_has_its_mirror_test():
    sanctioned_missing: set[str] = set()  # none today; additions need a reason here
    missing = []
    for src in sorted((ROOT / "planeops").rglob("*.py")):
        if "__pycache__" in str(src):
            continue
        rel = src.relative_to(ROOT / "planeops")
        if src.name == "__init__.py":
            pkg = rel.parent
            if str(pkg) == "." or not _has_logic(src):
                continue  # version-only root / namespace-only packages
            own_dir = ROOT / "tests" / pkg
            expected = (
                own_dir / f"test_{pkg.name}.py"
                if own_dir.is_dir()
                else ROOT / "tests" / pkg.parent / f"test_{pkg.name}.py"
            )
        else:
            expected = ROOT / "tests" / rel.parent / f"test_{rel.stem.strip('_')}.py"
        rel_expected = str(expected.relative_to(ROOT))
        if not expected.exists() and rel_expected not in sanctioned_missing:
            missing.append(f"{src.relative_to(ROOT)} -> {rel_expected}")
    assert not missing, "modules without a mirror test:\n" + "\n".join(missing)


def test_no_unanchored_observed_paths_in_output():
    # Output lines anchor state paths to the instance; a bare "-> observed/..."
    # sent a user hunting for a directory that is not where they stand
    # (found twice on live walks after a file-scoped fix missed siblings).
    from pathlib import Path

    offenders = [
        str(p)
        for p in Path("planeops").rglob("*.py")
        if "-> observed/" in p.read_text()
    ]
    assert not offenders, f"unanchored output paths in: {offenders}"


def test_third_party_libraries_live_only_in_their_provider_ring():
    # The providers ring: each third-party import name has ONE sanctioned home
    # under planeops/providers/. An import anywhere else fails the suite, so
    # "switching a library is one leaf file" is a proven property, not a hope.
    import re
    from pathlib import Path

    ring = {
        "ruamel": "planeops/providers/yaml",
        "yaml": "planeops/providers/yaml",  # the old direct pyyaml habit
    }
    offenders = []
    for p in Path("planeops").rglob("*.py"):
        rel = str(p)
        for lib, home in ring.items():
            if rel.startswith(home):
                continue
            pattern = rf"^\s*(import {lib}\b|from {lib}[.\s])"
            for i, line in enumerate(p.read_text().split("\n"), 1):
                if re.match(pattern, line):
                    offenders.append(f"{rel}:{i}: {line.strip()}")
    assert not offenders, "third-party import outside its ring:\n" + "\n".join(
        offenders
    )
