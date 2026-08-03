## What this changes

A short description of the change and why.

**Type:** feat / fix / docs / refactor / test / chore
**Breaking?** no, or: BREAKING (registry schema / CLI / config / adapter contract),
with the migration and the implied version bump (pre-1.0: breaking bumps minor).

## Checklist

- [ ] The gate passes locally: `uv run ruff check planeops tests && uv run ruff format --check planeops tests && uv run mypy && uv run pytest`
- [ ] Verified on macOS **and** Linux (the CI `integration` job covers Linux)
- [ ] Tests cover the change (`tests/` mirrors `planeops/` one-to-one)
- [ ] No new always-on process, no network call from the core, no secret value in
      code, snapshots, or reports
- [ ] A new adapter is a package under `planeops/adapters/` exposing `ADAPTER`; no
      central registry was edited
- [ ] `CHANGELOG.md` updated under `Unreleased` (right section; breaking prefixed **BREAKING:**)
