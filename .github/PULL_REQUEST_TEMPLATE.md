## What this changes

A short description of the change and why.

## Checklist

- [ ] The gate passes locally: `uv run ruff check engine tests && uv run ruff format --check engine tests && uv run mypy && uv run pytest`
- [ ] Tests cover the change (`tests/` mirrors `engine/` one-to-one)
- [ ] No new always-on process, no network call from the core, no secret value in
      code, snapshots, or reports
- [ ] A new adapter is a package under `engine/adapters/` exposing `ADAPTER`; no
      central registry was edited
- [ ] `CHANGELOG.md` updated under `Unreleased` if user-facing
