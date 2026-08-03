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
  <a href="#features">Features</a> ·
  <a href="#going-further">Docs</a> ·
  <a href="https://github.com/albertorsesc/planeops/blob/main/SPEC.md">Spec</a>
</p>

**planeops** is an inventory and drift detector for the AI tooling on your
machine: coding assistants, MCP servers, local models, background services, API
keys. You declare what should exist and why in plain YAML; planeops tells you
when reality disagrees, and changes nothing without showing the diff and asking
first.

```console
$ plane status --short
drift:6

$ plane drift
6 alert(s), 0 report, 2 uncovered -> ~/planeops/observed/mymac/DRIFT.md

$ cat ~/planeops/observed/mymac/DRIFT.md
# DRIFT
...
## Alerts (6)
- `launchd/ai.gateway` (unregistered): ungoverned always-on service;
  declare it or add an unmanaged glob
- `ollama/qwen3:8b` (active): expected present, not observed
...
```

*A machine with six things running that nobody wrote down, caught by one
read-only scan.*

## Why

Your machine accretes AI tooling: coding harnesses, MCP servers wired into
three different clients, local models, background services, API keys in
dotfiles. Nobody writes down what is installed, how it is wired, or why it is
there. Six months later, something is listening on a port and you cannot say
what put it there.

<p align="center">
  <img src="https://raw.githubusercontent.com/albertorsesc/planeops/main/docs/assets/drift-to-governed.png" alt="An ungoverned pile of tools on the left; the same tools declared and connected on the right" width="720">
</p>

planeops turns the pile into a registry: every asset declared with its reason
for existing, every scan diffed against that intent, every fix a rendered
change you confirm one at a time.

## Features

- **Catches what package managers can't**: ungoverned always-on services, an MCP server wired into one client but not the others, a pruned model your tooling depends on.
- **One loop, three verbs**: `observe` scans read-only, `drift` diffs desired against observed, `apply` converges with per-change confirmation.
- **No daemon, no open ports**: every command exits; the ambient loop is your OS scheduler running `plane reconcile`.
- **Onboarding is pruning, not authoring**: `plane init --seed` proposes the registry from what is already installed.
- **Typos are load errors**: `tolerence:` fails with "did you mean 'tolerance'?", never a silent no-op.
- **Secrets stay references**: names and presence are tracked; a value is only ever written to the one file its entry declares.
- **Exit codes are a contract**: `0` clean, `1` operator error, `2` drift, so your prompt and your cron both know the state.
- **Provider-neutral core**: adapters, schedulers, and stores are discovery seams; a fitness test bans vendor names from the engine.

## Install

```console
$ uv tool install planeops        # or: pipx install planeops / pip install planeops
```

Installs the `plane` command. Python 3.12+, macOS and Linux.

Want your AI assistant to query the plane over MCP? Install the extra:
`uv tool install "planeops[mcp]"` (adds `plane-mcp`).

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
$ plane init --seed
create the instance at /Users/you/planeops? (path or Enter to accept)
instance ready at /Users/you/planeops
  wrote 73 entries to /Users/you/planeops/registry/imported.yaml; prune, then `plane drift`

# scan the machine, diff it against the registry
$ plane observe
$ plane drift
0 alert(s), 3 report, 0 uncovered -> /Users/you/planeops/observed/mymac/DRIFT.md

# keep it fresh: an OS timer, previewed and confirmed
$ plane schedule --every 6h

# one glance forever after (empty means clean; wire it into your prompt)
$ plane status --short
drift:3
```

From there, `plane apply` walks the drift one confirmed change at a time.

`plane init` created an **instance**: a directory that is yours, not the
tool's. Git it like a dotfiles repo:

```
~/planeops/
├── registry/           desired state: the YAML you declare, edit, and prune
├── instance.yaml       this machine's adapter settings
├── secrets.sops.yaml   encrypted values, if you use the secrets store
└── observed/<host>/    generated per machine: snapshot.json, DRIFT.md
```

`registry/` and `instance.yaml` are your setup's documentation; `observed/` is
regenerated by every scan. Layout, multi-machine use, and the tool's exact
footprint: [docs/instance.md](https://github.com/albertorsesc/planeops/blob/main/docs/instance.md).

## Going further

- [SPEC.md](https://github.com/albertorsesc/planeops/blob/main/SPEC.md): the architecture, entry schema, adapter contracts, and exit codes.
- [docs/instance.md](https://github.com/albertorsesc/planeops/blob/main/docs/instance.md): your instance directory, several machines on one registry, the tool's footprint.
- [docs/secrets.md](https://github.com/albertorsesc/planeops/blob/main/docs/secrets.md): the four-step secrets flow (declare, `secrets init` once per machine, `secrets add` per value, `apply` materializes) and how values stay sealed.
- [docs/mcp.md](https://github.com/albertorsesc/planeops/blob/main/docs/mcp.md): every MCP server across every client in one view, and the read-only server your assistant can query.
- [CHANGELOG.md](https://github.com/albertorsesc/planeops/blob/main/CHANGELOG.md): releases and what is coming.

## What planeops is not

- **Not a runtime.** It never sits in any request path and starts no long-running process.
- **Not an installer.** Adapters shell out to the tools you already trust (`brew`, `systemctl`, `ollama`); planeops decides *whether*, they do *how*.
- **Not a fleet manager.** One human, their machines, their intent. Multi-host is on the roadmap as bundles of the same registry, not an agent mesh.

## Status

Pre-1.0: the loop, eleven adapters, scheduling, secrets, importers, and the MCP
server work on macOS and Linux and govern this project's own machines daily.
Contracts may still move; a breaking change bumps the minor and lands in the
[CHANGELOG](https://github.com/albertorsesc/planeops/blob/main/CHANGELOG.md)
with its migration.

## Built on

planeops delegates instead of reinventing: [sops](https://github.com/getsops/sops)
and [age](https://github.com/FiloSottile/age) hold the secrets,
[chezmoi](https://github.com/twpayne/chezmoi) reproduces config files, your
OS's own scheduler runs the ambient loop, and the package managers you already
use keep doing the installing. The engine rides on
[ruamel.yaml](https://sourceforge.net/projects/ruamel-yaml/) (its one runtime
dependency) and the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
for the optional server, and is built with [uv](https://github.com/astral-sh/uv),
[ruff](https://github.com/astral-sh/ruff), [mypy](https://github.com/python/mypy),
and [pytest](https://github.com/pytest-dev/pytest). Thanks to all of them.

## Contributing, security, license

[`CONTRIBUTING.md`](https://github.com/albertorsesc/planeops/blob/main/CONTRIBUTING.md)
has the dev setup, the quality gate, and how to write an adapter. Security
posture and reporting:
[`SECURITY.md`](https://github.com/albertorsesc/planeops/blob/main/SECURITY.md).
Licensed [Apache-2.0](https://github.com/albertorsesc/planeops/blob/main/LICENSE).
