<p align="center">
  <img src="https://raw.githubusercontent.com/albertorsesc/planeops/main/docs/assets/banner.png" alt="planeops: a control plane for a personal AI setup" width="720">
</p>

<p align="center">
  <a href="https://github.com/albertorsesc/planeops/actions/workflows/ci.yml"><img src="https://github.com/albertorsesc/planeops/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://codecov.io/gh/albertorsesc/planeops"><img src="https://codecov.io/gh/albertorsesc/planeops/graph/badge.svg" alt="Coverage"></a>
  <a href="https://scorecard.dev/viewer/?uri=github.com/albertorsesc/planeops"><img src="https://api.scorecard.dev/projects/github.com/albertorsesc/planeops/badge" alt="OpenSSF Scorecard"></a>
  <a href="https://pypi.org/project/planeops/"><img src="https://img.shields.io/pypi/v/planeops.svg" alt="PyPI"></a>
  <a href="https://pypi.org/project/planeops/"><img src="https://img.shields.io/pypi/pyversions/planeops.svg" alt="Python versions"></a>
  <img src="https://img.shields.io/badge/platform-macOS%20%7C%20Linux-8250df.svg" alt="Platforms: macOS and Linux">
  <a href="https://github.com/albertorsesc/planeops/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue.svg" alt="License: Apache-2.0"></a>
</p>

<p align="center">
  <a href="#what-it-sees">Coverage</a> ·
  <a href="#install">Install</a> ·
  <a href="#quickstart">Quickstart</a> ·
  <a href="#the-commands">Commands</a> ·
  <a href="#going-further">Docs</a> ·
  <a href="https://github.com/albertorsesc/planeops/blob/main/SPEC.md">Spec</a>
</p>

<h3 align="center">Write down your AI setup once.<br>Find out the moment reality disagrees.</h3>

**planeops** keeps an inventory of the AI tooling on your machine and tells you
when it stops matching what you meant: the coding assistants and their hooks,
MCP servers and which clients they are wired into, local models, background
services, packages, config, and API keys. You declare what should exist and why
in plain YAML. One read-only scan compares that to the machine. Nothing is
changed until you have seen the diff and said yes.

```console
$ plane drift
✗ 5 alert(s) on mymac 09:14

alerts (5)
  launchd
  ✗ ai.gateway           expected present, not observed
  ✗ com.example.updater  ungoverned always-on service; declare it or name it exactly in unmanaged
  ollama
  ✗ qwen3:8b   expected present, not observed
  ✗ legacy-7b  listed retired but still observed present
  secrets · required secret is not configured
    ✗ router-api-key

  full report ~/planeops/observed/mymac/DRIFT.md
```

*One scan, five alerts, four kinds of problem: a service that stopped, a service
that installed itself and runs at login, a model a cleanup pruned, a model you
retired that is still taking disk, and a key nothing ever configured.*

## Why

Your machine accretes AI tooling. A coding assistant here, its hooks running
shell on every tool call. MCP servers wired into one client and forgotten in
the other three. Local models from an experiment you finished months ago.
Background agents that installed themselves at login. Keys in dotfiles, in
`.env` files, in your shell profile.

None of it is written down. There is no record of what is installed, how it is
wired, or why you put it there. So the questions that matter have no answer:
what is running right now that I did not choose? What broke when I reinstalled?
What can I safely delete?

<p align="center">
  <img src="https://raw.githubusercontent.com/albertorsesc/planeops/main/docs/assets/drift-to-governed.png" alt="An ungoverned pile of tools on the left; the same tools declared and connected on the right" width="720">
</p>

planeops turns the pile into a registry. Every asset is declared with the
reason it exists, every scan is diffed against that intent, and every fix is a
rendered change you confirm one at a time.

## Highlights

- **One scan, thirteen adapters.** Services, models, four package managers,
  MCP clients, assistant hooks, secret stores, and the config traces tools
  leave behind, in a single read-only pass.
- **Observation never writes.** No daemon, no background process, no open
  port. `plane observe` reads the machine and writes one snapshot file.
- **Nothing mutates behind your back.** `plane apply` renders each change as a
  diff and asks, one entry at a time.
- **It knows how to be quiet.** A dormant project is `parked`, so silence is
  correct. A finished retirement asks you to tidy the registry instead of
  alerting forever. Per-entry tolerance decides what is worth waking you for.
- **Every MCP server across every client, in one view.** Claude Code, Claude
  Desktop, Cursor, and Codex, merged, so a server wired into one and missing
  from the rest is visible.
- **Secrets stay sealed.** Names and presence are tracked in the open, values
  are encrypted at rest with sops and age and never enter a snapshot or a
  report.
- **Ambient without a daemon.** `plane schedule` hands the loop to launchd or
  systemd, and `plane status --short` puts the result in your shell prompt.
- **Scriptable by design.** Exit `0` clean, `1` operator error, `2` drift, with
  `--json` on the reporting commands.
- **Names no vendor.** Adapters, platforms, schedulers, secret stores, MCP
  clients, and assistant harnesses are all discovery seams. Adding one is a
  new file, not a patch to the engine.

## What it sees

Thirteen adapters ship today, each observing a domain the others do not. The
ones that need configuration (`mcp` sources, `footprint` roots, the `secrets`
store) do nothing at all until you set them up.

| Adapter | What it tracks |
| --- | --- |
| `launchd` | macOS user agents: loaded, running, and whether they start themselves at login |
| `systemd` | Linux user units: enabled, active, and the same login question |
| `mcp` | MCP servers merged across Claude Code, Claude Desktop, Cursor, and Codex, with the scope each wiring uses |
| `harness` | Hooks your coding assistant runs on its own events, including whether the script they point at still exists |
| `ollama` | Local models, by name and digest |
| `pkg-brew` | Homebrew formulae, with versions |
| `pkg-npm` | npm globals |
| `pkg-uv` | uv tools |
| `pkg-nvm` | Node versions installed under nvm |
| `chezmoi` | Config files reproduced from a chezmoi source, and whether they have drifted from it |
| `footprint` | Tools discovered by the config directories they leave behind, which is how things nothing else tracks get found |
| `secrets` | Which declared secrets exist in the store, by name and presence only |
| `manual` | Anything without an adapter yet, held by a dated attestation that goes stale after 30 days |

An entry whose adapter does not exist yet is reported as uncovered rather than
as a violation, so you can declare a thing before planeops can see it.

## Install

```console
$ uv tool install planeops        # or: pipx install planeops / pip install planeops
```

Installs the `plane` command. Python 3.12+, macOS and Linux.

To let your AI assistant query the plane over MCP, install the extra:
`uv tool install "planeops[mcp]"`, which adds `plane-mcp`.

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
# scaffold an instance and seed the registry from what is already installed
$ plane init --seed
create the instance at /Users/you/planeops? (path or Enter to accept)
instance ready at /Users/you/planeops
  wrote 73 entries to /Users/you/planeops/registry/imported.yaml; prune, then `plane drift`

# scan the machine, then diff it against the registry
$ plane observe
✓ observed 73 facts on mymac /Users/you/planeops/observed/mymac/snapshot.json
  pkg-brew 21 · mcp 14 · ollama 9 · pkg-npm 8 · launchd 6 · ...
$ plane drift
✓ no drift on mymac 16:04

# hand the loop to your OS timer, previewed and confirmed
$ plane schedule --every 6h

# one glance, forever after (prints nothing when clean)
$ plane status --short
drift:3
```

`plane init --seed` drafts the registry from what you already have, so the
first pass is pruning rather than authoring. From there, `plane apply` walks
the drift one confirmed change at a time.

## The commands

| Command | Does |
| --- | --- |
| `plane init` | Scaffold an instance, optionally seeding the registry from the machine (`--seed`). On an existing instance, `--sections` names the `instance.yaml` sections you have not adopted yet |
| `plane observe` | Scan the machine and write a snapshot. Read-only. `--attest` refreshes manual attestations |
| `plane drift` | Diff desired against observed, write `DRIFT.md` and `DRIFT.json`. `--json` for piping |
| `plane status` | Show the last report without rescanning. `--short` for a shell prompt |
| `plane apply` | Converge confirmed changes one at a time. Narrow with `--id` or `--phase` |
| `plane reconcile` | Observe then drift in one pass, which is what a scheduler runs |
| `plane schedule` | Set up the ambient timer (`--every 6h`, `--no-login`, `--off`) |
| `plane secrets` | `init`, `add`, `list`, `remove` against the configured store |
| `plane import` | Propose entries from a manifest, an `.env` file, or the last snapshot. `--write` lands them |
| `plane mcp` | The cross-client MCP view. `mcp init` detects your clients and wires them as sources |

## How it stays quiet

An inventory that alerts on everything gets ignored. Two per-entry knobs decide
what reaches you, so a quiet report means the machine is genuinely fine.

**Lifecycle** says what you intend for a thing right now:

| Lifecycle | Means |
| --- | --- |
| `active` | In use. Missing is an alert |
| `maintain` | Kept working, not actively used. Missing is an alert |
| `parked` | Dormant on purpose. Absence is correct, so silence is correct |
| `retired` | Should be gone. Still observed is an alert, and once it is gone planeops asks you to delete the entry |
| `purge` | Same, and `apply` may also delete the artifact itself: the plist, the unit file, the client's MCP block |

**Tolerance** says how loudly a divergence lands: `auto` folds it, `report`
mentions it, `alert` wakes you. A version bump inside a major can fold while a
dead heartbeat alerts.

## Read-only by default, gated when it writes

<p align="center">
  <img src="https://raw.githubusercontent.com/albertorsesc/planeops/main/docs/assets/observe-gated.png" alt="An eye for read-only observation; a locked gate for confirmed mutation" width="620">
</p>

`observe`, `drift`, `status`, and `mcp` only read. The one command that changes
your machine is `apply`, and it renders each change as a diff and waits for
your confirmation before every single one. Adapters shell out to the tools you
already trust, so `brew`, `systemctl`, and `ollama` do the work; planeops
decides whether, they decide how.

A typo in the registry fails at load rather than quietly meaning nothing, which
is the same reason an unknown key is rejected instead of ignored.

## Secrets

<p align="center">
  <img src="https://raw.githubusercontent.com/albertorsesc/planeops/main/docs/assets/secrets-vault.png" alt="A safe holding a key, its value redacted" width="380">
</p>

Declare a secret like any other entry and planeops tracks whether it is
configured, never what it holds. Values are encrypted at rest with
[sops](https://github.com/getsops/sops) and
[age](https://github.com/FiloSottile/age), and at apply time they are written
only into the file the declaring entry names.

```console
$ plane secrets add router-api-key      # prompted, or piped
$ plane secrets list                    # names only
router-api-key
gateway-token
```

A value never enters a snapshot, a report, or a log line. Details in
[docs/secrets.md](https://github.com/albertorsesc/planeops/blob/main/docs/secrets.md).

## Your instance

`plane init` creates an **instance**: a directory that belongs to you, not to
the tool. Git it like a dotfiles repo.

```
~/planeops/
├── registry/           desired state: the YAML you declare, edit, and prune
├── instance.yaml       this machine's adapter settings
├── secrets.sops.yaml   encrypted values, if you use the secrets store
└── observed/<host>/    generated per machine: snapshot.json, DRIFT.md
```

`registry/` and `instance.yaml` are your setup's documentation. `observed/` is
regenerated by every scan, and one registry can serve several machines, each
with its own snapshot. Layout, multi-machine use, and the tool's exact
footprint: [docs/instance.md](https://github.com/albertorsesc/planeops/blob/main/docs/instance.md).

## Your assistant can read the plane

With the `[mcp]` extra, `plane-mcp` serves five tools over stdio: rescan the
machine, get the drift report, get the last report without rescanning, get the
cross-client MCP view, and list secret names. Your assistant answers "what
changed on this machine?" from the real snapshot instead of guessing.

There are deliberately no mutation tools. `apply` stays behind the CLI's
per-change confirmation, so an assistant can read the plane and never converge
it unattended.

## Going further

- [SPEC.md](https://github.com/albertorsesc/planeops/blob/main/SPEC.md): architecture, entry schema, adapter contracts, exit codes.
- [docs/instance.md](https://github.com/albertorsesc/planeops/blob/main/docs/instance.md): your instance directory, several machines on one registry, the tool's footprint.
- [docs/secrets.md](https://github.com/albertorsesc/planeops/blob/main/docs/secrets.md): the secrets flow end to end and how values stay sealed.
- [docs/mcp.md](https://github.com/albertorsesc/planeops/blob/main/docs/mcp.md): the cross-client view, the opt-in unwire of retired servers, and the read-only server your assistant queries.
- [docs/footprint.md](https://github.com/albertorsesc/planeops/blob/main/docs/footprint.md): discovering tools by their config traces, and keeping debris out of the way.
- [CONTRIBUTING.md](https://github.com/albertorsesc/planeops/blob/main/CONTRIBUTING.md): dev setup, the quality gate, and how to write an adapter.
- [CHANGELOG.md](https://github.com/albertorsesc/planeops/blob/main/CHANGELOG.md): every release and what changed.

## Status

Pre-1.0, and it governs this project's own machines daily. The loop, thirteen
adapters, scheduling, secrets, importers, and the MCP server all work on macOS
and Linux, with both covered by CI on every change. Contracts may still move; a
breaking change bumps the minor and lands in the
[CHANGELOG](https://github.com/albertorsesc/planeops/blob/main/CHANGELOG.md)
with its migration.

## Built on

planeops delegates instead of reinventing.
[sops](https://github.com/getsops/sops) and
[age](https://github.com/FiloSottile/age) hold the secrets,
[chezmoi](https://github.com/twpayne/chezmoi) reproduces config files, your
OS's own scheduler runs the ambient loop, and the package managers you already
use keep doing the installing. The engine rides on
[ruamel.yaml](https://sourceforge.net/projects/ruamel-yaml/) for the registry,
[Rich](https://github.com/Textualize/rich) with
[rich-argparse](https://github.com/hamdanal/rich-argparse) for the console, and
the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) for
the optional server, and is built with [uv](https://github.com/astral-sh/uv),
[ruff](https://github.com/astral-sh/ruff), [mypy](https://github.com/python/mypy),
and [pytest](https://github.com/pytest-dev/pytest). Thanks to all of them.

## Contributing, security, license

Contributions are welcome: fork, branch, and open a PR.
[`CONTRIBUTING.md`](https://github.com/albertorsesc/planeops/blob/main/CONTRIBUTING.md)
has the dev setup, the quality gate, and a walkthrough of writing an adapter.
Security posture and reporting:
[`SECURITY.md`](https://github.com/albertorsesc/planeops/blob/main/SECURITY.md).
Licensed [Apache-2.0](https://github.com/albertorsesc/planeops/blob/main/LICENSE).
