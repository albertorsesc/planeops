# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project aims
to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `plane mcp`: a read-only cross-client view of MCP servers from the last snapshot.
  Lists each server and the clients it is wired into, and flags servers wired into
  only one client (reuse candidates), the same tool under different names across
  clients (naming drift), and servers observed but absent from the registry
  (ungoverned). `--json` emits the structured view. Pure read with the same
  no-recompute posture as `plane status`; reads what `plane observe` already wrote,
  never scans the machine. This is the observability half of MCP management; wiring
  servers across clients (converge) stays deferred behind `plane apply`.
- Optional read-only MCP server (`plane-mcp`, install with the `mcp` extra) exposing
  two tools, `tarmac_observe` (inventory the machine) and `tarmac_drift` (structured
  drift, the same shape as `plane drift --json`). Both are annotated read-only; there
  are deliberately no mutation tools, so an assistant can read state but converging
  drift stays behind `plane apply`'s per-change confirmation. The logic is a thin
  pass-through to `run_observe`/`run_drift` (no re-implemented triage), and the core
  CLI carries no MCP dependency.
- Engine core: entry schema, the `observe`/`plan`/`execute` adapter contract,
  package-scan adapter discovery, and an injectable platform seam.
- Platform implementations are discovered by package scan and selected by a
  declared `sys_platforms` selector (no OS if/elif); a `linux` platform ships
  alongside `darwin` so the engine runs off macOS.
- `systemd` adapter: Linux user-service parity to `launchd`. Observes each user
  unit's enabled and active state (`systemctl --user is-enabled`/`is-active`, by
  exit code) and converges via `enable --now`/`disable --now`; a `purge` entry also
  removes the unit file. Has a real-`systemctl` integration test that runs where a
  `systemd --user` session exists (the CI Linux job sets one up).
- Integration tests exercise the real external tools instead of faked runners:
  `sops`/`age`/`chezmoi`, and `launchctl` on macOS. Each skips when its tool is
  absent, so the default gate stays green. A CI job installs sops/age/chezmoi on
  Linux and runs them on every PR; the launchd test runs on macOS against a
  throwaway agent loaded from a temp plist and booted out in teardown, so real
  services are never touched.
- `plane` CLI with four verbs: `observe`, `drift`, `apply`, and `import`.
- Importers are discovered by package scan, like adapters: each exposes a module
  `IMPORTER`, and the CLI learns its `import` kinds from discovery rather than a
  central list. `import stackfile` seeds entries from a stack manifest;
  `import envfile` proposes `secrets/<name>` entries from a `.env` file, reading
  only the keys (values are discarded, never printed or stored).
- `import observed` scaffolds the registry from the machine's own `observe`
  snapshot, so onboarding is prune-a-list rather than hand-author-from-blank: it
  proposes one entry per observed item not already declared (each `active`, marked
  to verify), grouped by adapter. `--adapter <name>` scopes the proposal to one
  type, so a stack is onboarded a slice at a time. Writes nothing; the CLI prints
  the proposal for review.
- `manual` adapter: attestation-based observation for assets without a
  dedicated adapter, with 30-day staleness.
- `launchd` adapter: observes user LaunchAgents (loaded/running state) and
  converges them via `plan`/`execute` (bootout a retired-but-loaded service,
  bootstrap an active-but-unloaded one), gated by per-change confirmation.
- `pkg-brew` adapter: observes installed Homebrew formulae and their versions,
  and converges presence via `plan`/`execute` (install an absent active formula,
  uninstall a present retired one).
- `ollama` adapter: observes local models (recording each model's digest as its
  version), and converges presence via `plan`/`execute` (pull an absent active
  model, remove a present retired one).
- `pkg-uv` adapter: observes tools installed via `uv tool install` and converges
  presence via `plan`/`execute`.
- `pkg-npm` adapter: observes global npm packages and converges presence via
  `plan`/`execute`.
- `pkg-nvm` adapter: observes node runtimes under `~/.nvm/versions/node`
  (observe-only, since nvm is a shell function rather than a binary).
- `mcp` adapter: reads MCP-server wirings from a configurable source list
  (`instance.yaml`'s `mcp.sources`) and merges them by name across tools, so a server wired
  into one tool but not another is visible as a reuse candidate. Observe-only,
  and names no specific tool: the sources are configuration, not code.
- `Ctx` now carries the instance `repo_root`, so an adapter can read
  instance-level configuration.
- Per-machine adapter settings are consolidated into one `instance.yaml`
  (sectioned by concern: `mcp.sources`, `importer.rules`, `secrets.store`),
  replacing separate `mcp-sources.yaml` and `stackfile-mapping.yaml` files.
- `chezmoi` adapter: delegates config/dotfile reproduction to chezmoi. Observes
  managed files and their drift (`chezmoi status`) and converges a drifted file by
  invoking `chezmoi apply`; chezmoi owns the writing, secrets, and templating while
  tarmac governs it as one domain.
- Drift triage surfaces a general content-drift signal (`facts.drifted`) from any
  adapter, routed by the entry's tolerance.
- `plane apply` records every run to an immutable `applied.jsonl`, re-observes so
  drift reflects it, honors `owner: human` (never writes it), converges in `phase`
  order, and contains a crashing adapter instead of aborting the run.
- `secrets` adapter and a sops backend: track whether each declared secret is
  configured, read from a sops store's key structure without decrypting a value.
  A declared-but-unconfigured secret is an alert.
- Redaction gate: `ctx.secrets` is a presence-only handle during observe, plan,
  and every non-secrets execute, so requesting a value raises `RedactionError`. The
  engine builds a value-capable handle only for the secrets adapter's confirmed
  execute, so a secret value cannot reach a snapshot, a report, or the journal on
  the ordinary paths.
- Secrets materialization: at apply time the `secrets` adapter writes a secret's
  value into the injection targets a consumer declares
  (`secrets: [{ref, injected_as: file:<path>#KEY}]`), decrypting via `sops -d`. The
  confirmation diff and the journal are value-redacted; the value lands only in the
  target file (created 0600, replaced atomically, symlinked targets refused).
- Injection-path containment: a materialized secret may only be written into the
  instance repo, the home directory, or a base listed in `instance.yaml`'s
  `secrets.allow_targets`. A target that resolves outside every base (including via
  a symlinked ancestor directory) is refused, so a secret can't be redirected out
  of trusted space.
- `DRIFT.md` report with Alerts / Report / Auto-folded / Uncovered / Re-auth
  sections, and a non-zero exit code when alerts exist.
- `plane drift` also writes a machine-readable `DRIFT.json` beside `DRIFT.md`, and
  `plane drift --json` prints that structured report to stdout. Same triage as the
  markdown pane (a versioned schema, per-section items, and an `exit_code` mirroring
  the process exit), so a drift notification or an MCP surface reads structured data
  instead of scraping markdown.
- `plane status` shows the last drift report without recomputing: a pure, instant read
  of `DRIFT.json` (no machine scan, no writes), with `--short` for a shell-prompt
  indicator (prints nothing when clean) and `--json` to emit the stored report. Exit
  code mirrors drift (2 when alerts exist), so it composes into prompts and scripts.
- Entries may declare `needs: [id, ...]`, the entries they depend on (cross-adapter).
  Drift alerts when an `active` entry needs something that is being retired/purged or
  is observed absent, so a resource a consumer depends on (e.g. an embedding model a
  tool uses) can't be pruned out from under it.

[Unreleased]: https://github.com/albertorsesc/tarmac/commits/main
