# Dev tasks. `make check` is the full gate (lint, format check, type check, tests),
# the same checks CI runs. `make test` auto-fixes lint/formatting first, then runs
# `make check` — local convenience; don't wire `make test` into CI (it mutates files).
#
# The plane helpers target a plane instance via REPO, defaulting to the repo root
# (its example registry). Point them at a private instance with, e.g.:
#   make drift REPO=path/to/instance

REPO ?= .

.PHONY: test fix check lint fmt-check typecheck unit observe drift status reconcile

test: fix check          ## auto-fix, then run the full gate

fix:                     ## auto-fix lint + formatting
	uv run --frozen ruff check --fix planeops tests
	uv run --frozen ruff format planeops tests

check: lint fmt-check typecheck unit   ## the full gate, no mutations

lint:
	uv run --frozen ruff check planeops tests

fmt-check:
	uv run --frozen ruff format --check planeops tests

typecheck:
	uv run --frozen mypy

unit:
	uv run --frozen pytest -q

observe:                 ## scan the machine (REPO=<instance>)
	uv run --frozen plane --repo $(REPO) observe

drift:                   ## diff desired vs observed (REPO=<instance>)
	uv run --frozen plane --repo $(REPO) drift

status:                  ## show the last drift report (REPO=<instance>)
	uv run --frozen plane --repo $(REPO) status

reconcile: observe drift ## observe then drift
