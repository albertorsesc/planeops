<p align="center">
  <img src="https://raw.githubusercontent.com/albertorsesc/planeops/main/docs/assets/banner.png" alt="planeops: a control plane for a personal AI setup" width="720">
</p>

<p align="center">
  <a href="https://github.com/albertorsesc/planeops/actions/workflows/ci.yml"><img src="https://github.com/albertorsesc/planeops/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/planeops/"><img src="https://img.shields.io/pypi/v/planeops.svg" alt="PyPI"></a>
  <a href="https://github.com/albertorsesc/planeops/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue.svg" alt="License: Apache-2.0"></a>
  <img src="https://img.shields.io/badge/python-3.12%2B-blue.svg" alt="Python 3.12+">
</p>

<p align="center">
  <a href="#install">Install</a> ·
  <a href="#quickstart">Quickstart</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#secrets-without-values">Secrets</a> ·
  <a href="#let-your-assistant-read-the-plane">MCP</a> ·
  <a href="https://github.com/albertorsesc/planeops/blob/main/SPEC.md">Spec</a>
</p>

**planeops** keeps the AI tooling on your machine declared, observed, and drift-free. No daemon, no agent, no background anything: short-lived commands that read your machine, tell you what changed, and never write without showing the diff and asking first.

```console
$ plane status --short
drift:6

$ plane drift
6 alert(s), 0 report, 2 uncovered -> observed/mymac/DRIFT.md

$ cat observed/mymac/DRIFT.md
# DRIFT
...
## Alerts (6)
- `launchd/ai.gateway` (unregistered): ungoverned always-on service;
  declare it or add an unmanaged glob
- `ollama/qwen3:8b` (active): expected present, not observed
...
```

*A machine with six things running that nobody wrote down, caught by one read-only scan.*

## Why

Your machine accretes AI tooling: coding harnesses, MCP servers wired into three different clients, local models, background services, API keys in dotfiles. Nobody writes down what is installed, how it is wired, or why it is there. Six months later, something is listening on a port and you cannot say what put it there.

<p align="center">
  <img src="https://raw.githubusercontent.com/albertorsesc/planeops/main/docs/assets/drift-to-governed.png" alt="An ungoverned pile of tools on the left; the same tools declared and connected on the right" width="720">
</p>

planeops turns the pile into a registry: every asset declared in plain YAML with its reason for existing, every scan diffed against that intent, every fix a rendered change you confirm one at a time.

## Highlights

- **Catches what a package manager can't.** Ungoverned always-on services, an MCP server wired into one client but not the others, the same tool under different names across clients, a dead reconcile heartbeat, a model your tooling depends on being pruned out from under it (`needs:`).
- **One loop, three verbs.** `observe` scans (read-only), `drift` diffs desired against observed, `apply` converges with a per-change confirmation. Exit codes are a contract: `0` clean, `1` operator error, `2` drift alerts, so your shell prompt and your cron both know the state.
- **No daemon, no open ports.** Every command exits. The ambient loop is your OS scheduler (launchd or systemd) running `plane reconcile`, set up by `plane schedule` and then governed like any other entry.
- **Writes are gated, always.** Only `apply` mutates, only after a rendered diff and a yes: per change, or pre-declared in the registry with `tolerance: auto` for the domains you trust. Everything else, including the MCP server your assistant talks to, is read-only by construction.
- **Onboarding is pruning, not authoring.** `plane init --seed` scans the machine and proposes the registry; you delete what you refuse to govern instead of writing YAML from scratch.
- **Typos are load errors, never silent no-ops.** `tolerence: alert` fails with "did you mean 'tolerance'?" instead of quietly not escalating. Every key in every file, same rule.
- **Secrets stay references.** Names and presence are tracked; values are decrypted only inside a confirmed materialization and land only in the declared target file. Snapshots, reports, and diffs never carry a value.
- **Provider-neutral by architecture.** Adapters, importers, platforms, schedulers, and secrets stores are five discovery seams; the core names no vendor (a test enforces it). Swap your secrets store and zero registry entries change.

## Install

```console
$ uv tool install planeops        # or: pipx install planeops / pip install planeops
```

Installs the `plane` command. Python 3.12+, macOS and Linux.

Want your AI assistant to query the plane over MCP? Install the extra: `uv tool install "planeops[mcp]"` (adds `plane-mcp`).

<details>
<summary>From source (development)</summary>

```console
$ git clone https://github.com/albertorsesc/planeops
$ cd planeops
$ uv sync            # engine + plane CLI
$ make check         # the full gate: lint, format, types, tests
```

</details>

## Quickstart

```console
# scaffold an instance and seed the registry from what's already installed
$ plane init ~/plane --seed
instance ready at /Users/you/plane
seeding the registry from this machine (observe -> import)...
  wrote 73 entries to /Users/you/plane/registry/imported.yaml; prune, then `plane drift`

# scan the machine, diff it against the registry
$ plane observe
observed 73 fact(s), 0 uncovered adapter(s) -> observed/mymac/snapshot.json
$ plane drift
0 alert(s), 3 report, 0 uncovered -> observed/mymac/DRIFT.md

# keep it fresh without thinking about it: an OS timer, previewed and confirmed
$ plane schedule --every 6h
$ plane apply --id launchd/ai.planeops.reconcile   # systemd/... on Linux

# one glance forever after (empty means clean; wire it into your prompt)
$ plane status --short
drift:3
```

From there: `plane apply` walks the drift as one confirmed change at a time, `plane mcp` shows every MCP server across all your clients and who has it wired, and `plane import observed --write` re-seeds the registry anytime.

## How it works

<p align="center">
  <img src="https://raw.githubusercontent.com/albertorsesc/planeops/main/docs/assets/observe-gated.png" alt="Observe eye and gated-write gauge" width="420">
</p>

The registry is desired state: one YAML entry per governed asset, carrying its adapter, lifecycle, and the intent sentence that says why it exists. `plane observe` asks each adapter to report what actually exists. `plane drift` triages the difference into alerts (a lifecycle violation, an ungoverned service), reports (worth a look), and auto-folded noise (an in-major version bump), written as `DRIFT.md` for you and `DRIFT.json` for machines.

Adapters teach the engine one kind of asset each: services (`launchd`, `systemd`), packages (`brew`, `npm`, `uv`, `nvm`), local models (`ollama`), config files (delegated to [chezmoi](https://github.com/twpayne/chezmoi)), MCP wiring, secrets. They are discovered by package scan, never registered in a central list, and the whole set is described in the [spec](https://github.com/albertorsesc/planeops/blob/main/SPEC.md).

## Secrets, without values

<p align="center">
  <img src="https://raw.githubusercontent.com/albertorsesc/planeops/main/docs/assets/secrets-vault.png" alt="A vault: keys visible, values sealed" width="360">
</p>

The shipped store is [sops](https://github.com/getsops/sops)+[age](https://github.com/FiloSottile/age): key names stay readable, values stay encrypted, so `plane observe` can answer "is the OpenRouter key configured?" without decrypting anything. A registry entry references `secret://openrouter-api-key`; which store serves it is instance configuration, so swapping stores touches zero entries. A value is decrypted exactly once, inside a confirmed `apply`, into the one file the entry declares (`0600`, symlink-refusing, containment-checked).

## Let your assistant read the plane

`plane-mcp` exposes four read-only tools over stdio: `planeops_observe`, `planeops_drift`, `planeops_status`, `planeops_mcp`. Your assistant can answer "what drifted on my machine this week?" and "which clients have the context7 server wired?" from real state instead of guessing. There are deliberately no mutation tools: converging stays behind the CLI's confirmation gate, in your terminal, under your fingers.

## What planeops is not

- **Not a runtime.** It never sits in any request path and starts no long-running process.
- **Not an installer.** Adapters shell out to the tools you already trust (`brew`, `systemctl`, `ollama`); planeops decides *whether*, they do *how*.
- **Not a fleet manager.** One human, their machines, their intent. Multi-host is on the [roadmap](https://github.com/albertorsesc/planeops/blob/main/CHANGELOG.md) as bundles of the same registry, not an agent mesh.

## Status

Pre-1.0: the loop, eleven adapters, scheduling, secrets, importers, and the MCP server work on macOS and Linux and govern this project's own machines daily. Contracts may still move; a breaking change bumps the minor and lands in the [CHANGELOG](https://github.com/albertorsesc/planeops/blob/main/CHANGELOG.md) with its migration. The next acceptance gate is a clean-machine reproduction rehearsal.

## Contributing, security, license

[`CONTRIBUTING.md`](https://github.com/albertorsesc/planeops/blob/main/CONTRIBUTING.md) has the dev setup, the quality gate, and how to write an adapter. Security posture and reporting: [`SECURITY.md`](https://github.com/albertorsesc/planeops/blob/main/SECURITY.md). Licensed [Apache-2.0](https://github.com/albertorsesc/planeops/blob/main/LICENSE).
