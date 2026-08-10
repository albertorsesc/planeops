# Contributing

Thanks for helping. This is the public engine repo; machine-specific data lives
in a separate private instance and never belongs here.

## Development setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/albertorsesc/planeops
cd planeops
uv sync
```

## The quality gate

Every change must pass all four checks. `make check` runs them (and `make test`
auto-fixes formatting first); CI runs the same ones on Python 3.12 and 3.13.

```bash
uv run ruff check planeops tests        # lint
uv run ruff format --check planeops tests  # formatting
uv run mypy                           # types (strict, planeops/)
uv run pytest                         # tests
```

`uv run ruff format planeops tests` applies formatting. Tests live in `tests/`,
mirroring `planeops/` one-to-one; a change ships with its tests.

## Writing an adapter

An adapter teaches the engine about one kind of asset. Adapters are discovered by
a package scan, so you never edit a central list.

1. Create a package under `planeops/adapters/<name>/`.
2. Implement the `Adapter` protocol from `planeops.core.contracts`: set `name` and
   `domains`, and implement `observe(ctx) -> list[Observed]` (read-only).
3. Expose the instance as a module-level `ADAPTER`. Discovery imports it and
   verifies it satisfies the contract.
4. To let the adapter converge its domain, also implement `MutatingAdapter`:
   `plan(entry, obs, ctx) -> list[Change]` (pure; `ctx` is always provided) and
   `execute(change, ctx) -> Result`. The engine renders each `Change` and takes
   a confirmation before calling `execute`; an adapter never mutates unprompted.
   Optionally declare `default_phase` (converge ordering; see SPEC section 5)
   and `EXECUTE_TIMEOUT` (`None` for confirmed long operations like installs,
   a bounded ceiling for quick service/config operations).
5. Add `tests/adapters/test_<name>.py` exercising `observe` (and `plan`)
   against recorded fixtures. No unit test touches the live machine; the shared
   conformance suite will fail until the new adapter is wired into it.

## Test layout (the mirror rule)

`tests/` shadows `planeops/` exactly, so knowing where code lives tells you where
its test lives:

- `planeops/<path>/<module>.py` -> `tests/<path>/test_<module>.py`.
- A package whose logic lives in `__init__.py` -> `tests/<path>/test_<package>.py`
  (e.g. `planeops/adapters/launchd/` -> `tests/adapters/test_launchd.py`).
- When a module grows several concerns, split the *implementation* into a
  package first (one module per concern) and mirror it, as `planeops/cli/` does
  with one module per verb; never let one test file become a junk drawer for a
  module that should be a package.
- Cross-cutting contract suites (`tests/core/test_conformance.py`,
  `tests/core/test_redaction.py`, and the tree-level
  `tests/test_architecture.py`, which enforces the layering rules and this very
  mirror rule in CI) sit beside what they enforce and are the sanctioned
  exceptions.
- Shared builders for one directory's tests live in that directory's
  `helpers.py` (e.g. `tests/cli/helpers.py`); fixtures go in `conftest.py`.
- `tests/integration/` is organized by scenario against real tools, a different
  axis than unit mirroring, deliberately.

## Design invariants

Hold these; a change that breaks one needs a very good reason:

- **No daemon, no open ports.** Every verb is a short-lived command.
- **Read by default.** Only `apply` writes, and only after a rendered diff and a
  per-change confirmation.
- **Secrets are references, never values.** No secret value enters the engine
  core, the repo, snapshots, or reports.
- **Provider-neutral.** No feature binds to a single vendor. Adapters shell out to
  local tools through the injected seam, with no network calls of their own.

## Commits, versioning, and PRs

Commits follow [Conventional Commits](https://www.conventionalcommits.org): a typed,
imperative subject under ~70 characters.

- Types: `feat`, `fix`, `docs`, `refactor`, `test`, `perf`, `chore`.
- A change that breaks the **registry schema, the CLI, the config format, or an
  adapter contract** is breaking: mark it `feat!:`/`fix!:` and add a `BREAKING CHANGE:`
  footer explaining the break and the migration.
- Add a body only when the reason isn't obvious from the diff; don't narrate tests.

Versioning is [SemVer](https://semver.org) with a [Keep a Changelog](https://keepachangelog.com)
`CHANGELOG.md`. Record user-facing changes under `Unreleased` in the right section
(`Added`/`Changed`/`Fixed`/`Deprecated`/`Removed`/`Security`), and prefix any breaking
entry with **BREAKING:**. Pre-1.0 (while `0.x`): a breaking change bumps the **minor**
(`0.MINOR.0`); features and fixes bump the **patch** (`0.x.PATCH`). After 1.0, standard
SemVer (breaking → major). One meaning carries through: the slot that moves is the one
that says "a contract moved", which is the minor until 1.0 and the major after it, so a
pin like `~=0.10.0` takes every fix and feature and stops exactly where reading is
required. Releases up to and including `0.10.0` bumped the minor for features too; from
`0.10.1` on, the minor is reserved for breaking changes as written here. CI enforces the
bump against the `Unreleased` sections, so the rule is checked rather than remembered.

The first published release is `0.1.0`, per the [SemVer FAQ](https://semver.org/#faq).
`1.0.0` is a stability commitment, deliberately deferred: it is cut when the registry
schema, the CLI, the config format, and the adapter contracts are stable enough that
other people's machines depend on them staying put, not at any feature milestone.

Open a PR against `main`; the template lists what to confirm, and the body should
state the change type and any breaking impact (and the version bump it implies).
