# tarmac

Reproduce, observe, and govern a personal AI setup as three planes.

[![CI](https://github.com/albertorsesc/tarmac/actions/workflows/ci.yml/badge.svg)](https://github.com/albertorsesc/tarmac/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)

A single machine accretes AI tools over time: coding harnesses, local models, MCP
servers, background services, API keys. Nobody writes down what is installed, how
it is wired, or why. `tarmac` makes that setup explicit and reproducible.
You declare what should exist in a registry, and the `plane` CLI observes what
actually exists, reports where the two disagree, and converges the difference one
confirmed change at a time.

It is a control plane, not a runtime. It reads state, renders diffs, and records
outcomes. It never sits in the request path of any agent, and it starts no
long-running process.

## The three planes

- **Control plane** decides what runs, where, and under which policy.
- **Data plane** is the executors that do the work: coding harnesses, agents, MCP
  servers, local models.
- **Management plane** is the single place the whole setup is configured,
  versioned, and observed. That is this repo.

## How it works

One loop, four verbs, a human in the reconcile seat:

```
observe  ->  drift  ->  apply
 (read)     (report)   (converge, per-change confirm)
```

- `plane observe` scans the machine and writes a snapshot. Read-only, safe to run
  on a schedule.
- `plane drift` diffs the registry (desired) against the snapshot (observed) and
  writes `DRIFT.md`: alerts, report, auto-folded version drift, uncovered entries,
  and a re-auth checklist. Exits non-zero when alerts exist.
- `plane apply` plans changes, renders each as a diff, and asks before every
  mutation. Nothing changes the machine without an explicit confirmation.
- `plane import stackfile <path>` proposes registry entries from an existing
  manifest. It writes nothing without confirmation.

Adapters teach the engine about one kind of asset each (a service manager, a model
runner, a package manager). They are packages under `engine/adapters/`, discovered
by a package scan, so adding one never edits a central list.

## Install

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/albertorsesc/tarmac
cd tarmac
uv sync
```

## Usage

```bash
# scan the machine and write observed/<host>/snapshot.json
uv run plane observe

# report where desired and observed disagree
uv run plane drift

# converge confirmed changes, one at a time
uv run plane apply --id launchd/ai.example.gateway

# seed a registry from an existing stack manifest
uv run plane import stackfile ./stack.md
```

`registry/example.yaml` shows the entry shape and every drift section without
assuming any particular tool. Copy it and describe your own machine.

## Governing your own scheduled script

A personal maintenance routine (a weekly updater, a backup job) is just a service,
so tarmac governs it without ever containing it:

1. Keep the script in your own instance, in a stable location that is **not** cloud-
   synced (a synced directory means anything that writes there silently changes code
   that later runs as you). `~/.local/libexec/` is a good home.
2. Point your scheduler at it (a `launchd` plist on macOS, a systemd timer on Linux).
   The plist/unit is machine state; it is never committed here.
3. Declare it as one `launchd/<label>` entry in your registry (see
   `com.example.weekly-maintenance` in the example). `plane drift` then tells you if
   the service goes missing or stops matching desired state.
4. Have the script end with `plane observe && plane drift`, so every run lands
   already observed and drift-checked.

The engine ships the adapter and this pattern; your actual script stays yours.

## Design principles

- **No daemon, no open ports.** Every verb is a short-lived command that exits.
- **Read by default.** Only `apply` writes, and only after a rendered diff and a
  per-change confirmation.
- **Secrets are references, never values.** The engine core, the repo, snapshots,
  and reports record references and metadata only.
- **Provider-neutral.** Nothing binds to one vendor. Adapters shell out to local
  tools through a single injected seam, with no network calls of their own.

`SPEC.md` is the authoritative build specification.

## Status and roadmap

Milestone M1 (the observe/drift engine, schema, `manual` and `launchd` adapters,
and `DRIFT.md` rendering) is implemented. See `CHANGELOG.md` for details.

- **M2**: package and runtime adapters (brew, npm, uv, node) with `plan`/`execute`.
- **M3**: coding-harness config, local-model, and MCP-server adapters.
- **M4**: sops+age secrets, materialization, re-auth checklist, and a clean-account
  reproduction rehearsal as the acceptance test.

## Repository layout

This is the public **engine** repo: the reusable engine, spec, example registry,
tests, and CI, with no machine-specific data. Real registry entries, generated
`observed/` snapshots, and secrets belong in a separate private instance.

```
engine/      core loop, schema, contracts, adapters, platform seam
registry/    example entries and unmanaged-glob rules
tests/       mirror engine/ one-to-one
SPEC.md      authoritative build spec
```

## Contributing, security, license

- [`CONTRIBUTING.md`](CONTRIBUTING.md): dev setup, the quality gate, and how to
  author an adapter.
- [`SECURITY.md`](SECURITY.md): reporting a vulnerability and the design posture.
- Licensed under [Apache-2.0](LICENSE).
