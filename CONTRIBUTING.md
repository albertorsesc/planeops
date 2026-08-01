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
uv run ruff check engine tests        # lint
uv run ruff format --check engine tests  # formatting
uv run mypy                           # types (strict, engine/)
uv run pytest                         # tests
```

`uv run ruff format engine tests` applies formatting. Tests live in `tests/`,
mirroring `engine/` one-to-one; a change ships with its tests.

## Writing an adapter

An adapter teaches the engine about one kind of asset. Adapters are discovered by
a package scan, so you never edit a central list.

1. Create a package under `engine/adapters/<name>/`.
2. Implement the `Adapter` protocol from `engine.core.contracts`: set `name` and
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

`tests/` shadows `engine/` exactly, so knowing where code lives tells you where
its test lives:

- `engine/<path>/<module>.py` -> `tests/<path>/test_<module>.py`.
- A package whose logic lives in `__init__.py` -> `tests/<path>/test_<package>.py`
  (e.g. `engine/adapters/launchd/` -> `tests/adapters/test_launchd.py`).
- When a module grows several concerns, split the *implementation* into a
  package first (one module per concern) and mirror it, as `engine/cli/` does
  with one module per verb; never let one test file become a junk drawer for a
  module that should be a package.
- Cross-cutting contract suites (`tests/core/test_conformance.py`,
  `tests/core/test_redaction.py`) sit beside the contracts they enforce and are
  the sanctioned exceptions.
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
SemVer (breaking → major).

Open a PR against `main`; the template lists what to confirm, and the body should
state the change type and any breaking impact (and the version bump it implies).
