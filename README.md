# planeops

Reproduce, observe, and govern a personal AI setup as three planes.

[![CI](https://github.com/albertorsesc/planeops/actions/workflows/ci.yml/badge.svg)](https://github.com/albertorsesc/planeops/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)

A single machine accretes AI tools over time: coding harnesses, local models, MCP
servers, background services, API keys. Nobody writes down what is installed, how
it is wired, or why. `planeops` makes that setup explicit and reproducible.
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

One loop, a human in the reconcile seat:

```
observe  ->  drift  ->  apply
 (read)     (report)   (converge, per-change confirm)
```

- `plane init [path]` scaffolds an instance (registry + a starter `instance.yaml`)
  and registers it in `~/.config/planeops/config.toml`, so the installed `plane` finds
  it from any directory. `--seed` then observes the machine and seeds the registry, so
  one command lands a governed registry to prune (`--no-seed` scaffolds only).
- `plane observe` scans the machine and writes a snapshot. Read-only, safe to run
  on a schedule.
- `plane drift` diffs the registry (desired) against the snapshot (observed) and
  writes `DRIFT.md` (the human pane) and `DRIFT.json` (the machine pane): alerts
  (including ungoverned always-on services and failed adapter scans), report,
  auto-folded version drift, uncovered entries, ungoverned observations, and a
  re-auth checklist. Exits non-zero when alerts exist. `--json` prints the
  report to stdout.
- `plane status` prints the last report without rescanning: instant and read-only.
  `--short` gives a shell-prompt indicator (the alert count, empty when clean).
- `plane reconcile` runs `observe` then `drift` in one pass (exit 2 on alerts). This
  is the one command a scheduler (a launchd agent or systemd timer) runs to keep drift
  current, so a `status --short` prompt stays fresh without you rescanning by hand.
- `plane schedule` sets that up: it previews and (after confirmation, `--yes`
  for scripts) writes an OS-native timer (launchd on macOS, systemd on Linux)
  that runs `plane reconcile` at login and on an interval (`--every 6h`,
  `--no-login`, `--off`), and declares it as a registry entry, so `plane apply`
  loads it through the confirm gate and `plane drift` then governs the schedule
  itself. The per-OS backends are discovered, not branched.
- `plane mcp` gives a cross-client view of MCP servers from the last snapshot: each
  server and the clients it is wired into, flagging servers wired into only one client
  (reuse candidates), the same tool under different names across clients (naming
  drift), and servers observed but not in the registry (ungoverned). Read-only;
  `--json` emits it structured.
- `plane apply` plans changes, renders each as a diff, and asks before every
  mutation. Nothing changes the machine without an explicit confirmation.
- `plane import <kind> [path]` proposes registry entries:
  `stackfile` from a hand-written manifest, `envfile` from a `.env` (key names only,
  values discarded), and `observed` from the machine's own snapshot, so onboarding
  is prune-a-list rather than author-from-blank. It prints by default; `--write` lands
  the proposal in `registry/imported.yaml` (de-duped, confirmed) for you to prune.
  `--adapter <type>` scopes a proposal to one kind.

Adapters teach the engine about one kind of asset each (a service manager, a model
runner, a package manager). They are packages under `engine/adapters/`, discovered
by a package scan, so adding one never edits a central list. An entry can also
declare `needs: [id, ...]`; drift alerts when an active entry's dependency is being
retired or is absent, so a model or package a tool relies on can't be pruned out
from under it.

Assistants can read the plane over an optional MCP server (`plane-mcp`, install the
`mcp` extra): `planeops_observe` inventories the machine, and the pure-read
`planeops_drift`, `planeops_status`, and `planeops_mcp` answer "what has drifted?",
"is there drift right now?" (no rescan), and "how are my MCP servers wired?", without
ever converging anything. Mutation stays behind the CLI's confirmation gate.

## Install

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/albertorsesc/planeops
cd planeops
uv sync                 # core engine + the `plane` CLI
uv sync --extra mcp     # optional: also install the `plane-mcp` assistant server
```

The distribution is named `planeops`; it installs the `plane` command (and
`plane-mcp` with the `mcp` extra).

`make test` runs the full gate (lint, format, type-check, tests); `make observe`,
`make drift`, and `make status` (with `REPO=<your-instance>`) wrap the common
commands so you don't retype `uv run plane --repo ...`.

### Finding your instance

`plane` locates the instance root (where `registry/` and `observed/` live) by
precedence: `--repo <path>`, else `$PLANEOPS_INSTANCE`, else
`~/.config/planeops/config.toml` (`instance = "/path/to/instance"`, honoring
`$XDG_CONFIG_HOME`), else the current directory walking up to a `.planeops` marker.
Drop a `.planeops` file at your instance root and point `config.toml` at it once, and
`plane` works from any directory. That home file holds only the pointer; state stays
under the instance.

## Usage

```bash
# one-time: scaffold an instance, register it, and seed the registry from the machine
uv run plane init ~/planeops-instance --seed

# scan the machine and write observed/<host>/snapshot.json
uv run plane observe

# report where desired and observed disagree (writes DRIFT.md + DRIFT.json)
uv run plane drift

# observe + drift in one pass (what a scheduler runs to keep drift current)
uv run plane reconcile

# set up the ambient reconcile timer (login + every 6h); `plane apply` then loads it
uv run plane schedule --every 6h

# show the last report without rescanning; --short drives a shell prompt
uv run plane status
uv run plane status --short          # e.g. "drift:3", prints nothing when clean

# cross-client view of MCP servers: which clients each is wired into, plus flags
uv run plane mcp

# seed the registry from what's already on the machine, then prune imported.yaml
# (the path defaults to this host's own snapshot)
uv run plane import observed --write

# converge confirmed changes, one at a time
uv run plane apply --id launchd/com.example.agent-gateway
```

`registry/example.yaml` shows the entry shape and the common drift situations
without assuming any particular tool. Copy it and describe your own machine.

## Governing your own scheduled script

A personal maintenance routine (a weekly updater, a backup job) is just a service,
so planeops governs it without ever containing it:

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

## Status

The observe/drift/apply loop runs on macOS and Linux, with adapters for services
(`launchd`, `systemd`), packages (`brew`, `npm`, `uv`), node runtimes (`nvm`), local
models (`ollama`), config files (delegated to `chezmoi`), MCP-server wiring
(read-only), and a `sops`+`age` secrets store (presence is tracked without
decrypting; a value is decrypted only inside a confirmed materialization and
lands only in its declared target file). One-command onboarding (`plane init` + instance resolution via
`~/.config/planeops`, `plane import observed --write` to seed the registry from the
machine), the `plane reconcile` ambient loop, structured `DRIFT.json`, `plane status`,
the cross-client `plane mcp` view, entry `needs` dependencies, and the optional MCP
server are all in place. See `CHANGELOG.md` for the full history.

Not yet: a tagged release / installable package, and a holistic clean-account
reproduction rehearsal as the end-to-end acceptance test.

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
