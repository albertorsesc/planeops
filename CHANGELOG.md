# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project aims
to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **BREAKING (pre-1.0):** the Python package is `planeops`, not `engine`.
  `pip install planeops` now installs `import planeops`; the maximally generic
  top-level name `engine` will never be claimed in anyone's site-packages. Done
  before the first release precisely because it could never be done after.
  Entry points, mypy/ruff targets, docs, and the architecture fitness tests all
  follow the rename; the conceptual word "engine" survives only as prose.
- **BREAKING (pre-1.0):** secrets stores are the fifth discovery seam. Store
  implementations live under `planeops/secrets/stores/`, one module per kind
  exposing a `STORE` provider; the resolution layer knows no concrete store
  (enforced by the architecture fitness tests), and even the default is the
  provider's own declaration. In `instance.yaml`, `secrets.store` now names the
  store KIND (`sops`, the default) and the sops file path moved to
  `secrets.path`; an old-style path in `store` fails loudly with the available
  kinds listed. The protocol is `SecretsStore` (was `SecretsBackend`), and
  `run_apply`'s injection parameter is `secrets_store`. Swapping or adding a
  store now touches zero engine code: drop a module in, it self-registers.
- The CLI is a package: one module per verb, each owning its command and its
  parser registration, with `planeops/cli/__init__.py` reduced to composition and
  the single operator-error choke point. Tests mirror the source tree
  one-to-one (`tests/cli/test_<verb>.py`, per-backend scheduler tests, per-OS
  platform tests), the mirror rule is codified in CONTRIBUTING, and the
  previously missing mirrors exist, so "tests mirror engine" is now literally,
  mechanically true.

### Fixed

- `phase` must be an integer and `pin` a string at registry load (a YAML
  `phase: "3"` used to load fine and then crash apply's phase sort). Every verb
  notes a resolution landing on a directory without the `.planeops` marker (the
  skipped-init trap), and `plane schedule` warns when the plane binary it bakes
  into the job does not exist yet.
- Hardening follow-ups from the audit: parents created for a materialized secret
  are 0700 (not the process umask, which undermined the 0600 file inside a
  listable directory); the systemd scheduler refuses a newline in the plane path
  or PATH (plain-text unit concatenation would have turned it into an injected
  directive); a secret name that cannot be safely quoted for `sops --extract` is
  refused before any shell-out; and `plane import observed` defaults to the
  host's own snapshot path instead of making the user retype a path the CLI
  already computes (other import kinds still require one). The home-directory
  containment base and the no-rotation-refresh behavior are now documented
  decisions in the code, not silences.
- The adapter contract is honestly typed: `plan(entry, obs, ctx)` requires its
  ctx (the engine always provides one; the optional-`None` form only invited
  None-guards for a case production never produces), and the platform None-guards
  in the chezmoi and secrets adapters are gone. Tests exercise the same contract
  production runs.
- Operator errors are handled once, uniformly. A bad registry edit (the most
  common newcomer mistake) now exits 1 with the schema message from every verb
  instead of tracebacking from `observe`/`drift`/`apply`; the handling lives at
  the CLI dispatch point, so every future verb inherits it. A torn or corrupt
  snapshot reads as one clean "no readable snapshot; run `plane observe` first"
  from `drift`/`apply` (shared torn-safe loader, same as the read verbs), and
  snapshot items missing their identifying keys are skipped instead of poisoning
  the run. `--json` is now a machine contract on every verb, `drift --json`
  included (a JSON error object on stdout, drift still exiting 1):
  `status --json` and `mcp --json`
  emit a JSON error object on stdout when unseeded instead of nothing. `plane
  status` degrades on a hand-edited or older-schema report instead of crashing.
  Malformed `secrets` refs on an entry fail at registry load with the entry
  named, instead of being silently skipped at materialization time.
- `plane schedule --no-login` now actually fires on Linux. The generated timer
  had only `OnUnitActiveSec`, which is relative to the service's last activation
  and so never elapses on a fresh enable (verified live: `NEXT` stayed empty
  forever); the timer now also carries `OnActiveSec`, so enabling it schedules
  the first run. The no-op `Persistent=` (calendar timers only) is dropped. And
  `plane schedule` now shows what it will write and asks before writing (job
  files + the registry entry), with `--yes` for scripts, the same confirm posture
  as `import --write`: no readable stdin and no `--yes` writes nothing.
- The apply journal is crash-safe: each record is appended the moment its change
  is decided, not batched at the end of the run, so a crash mid-apply still
  leaves every already-executed mutation on the record (previously such a crash
  left zero journal entries, exactly when the audit trail mattered most). And the
  documented converge order is now encoded: every mutating adapter declares its
  `default_phase` (packages 2, config 3, models 4, secrets 5, services 6), so
  unphased entries converge packages-first and load services last against
  complete config, instead of everything landing in one unordered bucket.
- Subprocess timeouts now match the operation instead of one global 30s ceiling.
  Confirmed converge operations that legitimately run long (`brew`/`npm`/`uv`
  installs, `ollama pull`) are unbounded, the human just confirmed the change and
  owns the wait; service and config operations (`launchctl`, `systemctl`,
  `chezmoi apply`) get a 300s ceiling so a hung tool can't wedge an apply run;
  `sops -d` gets 60s. A timeout is now distinct from a missing binary (exit 124
  vs 127) and says the underlying command may still be running, instead of both
  collapsing into the same failure. Observe probes keep the fast 30s default.
- A retired service now converges without `purge`. Drift treated "observed at all"
  as present, but the launchd/systemd adapters observe every service file on disk
  regardless of state, so a retired, booted-out service whose file remained alerted
  forever while `plane apply` had nothing left to do. Adapters now declare semantic
  presence (a `present` fact: loaded for launchd, enabled-or-active for systemd) and
  drift's retired check consumes it, so retired means "not running" and `purge`
  keeps meaning "file removed too". Package adapters are unchanged (installed is
  present).
- `plane drift` no longer stays silent about things it can see. A new **Ungoverned**
  section lists everything observed on the machine that is neither declared nor
  excluded by an unmanaged glob, and an ungoverned item whose own facts say it is
  always-on (a login/keepalive/interval launchd agent, an enabled systemd unit)
  raises an alert: software that installed itself into the boot path is the one
  thing a control plane must never miss. Adapters expose this as a general
  `always_on` fact. The JSON pane's `schema_version` bumps to 2 for the new
  section. Also, entries whose adapter crashed during observe now alert as
  "adapter scan failed; state unknown" instead of the false "expected present,
  not observed", and `plane observe` prints a warning per failed adapter.
- `plane apply` and `plane schedule` report the truth. A typo'd `--id` is a loud
  error instead of a false "machine matches desired state"; the no-changes message
  is now neutral and surfaces any standing drift alerts (services and config can't
  be planned from nothing, so "planned nothing" never meant "no drift"); a
  successful apply recomputes DRIFT.md/DRIFT.json so a shell prompt reflects the
  converge immediately instead of at the next scheduled reconcile; and
  `plane schedule` ends with its own observe, so the hinted `plane apply` sees the
  just-written job on first use.
- The MCP server resolves the instance the same way the CLI does
  ($PLANEOPS_INSTANCE, then the `~/.config/planeops` pointer, then the marker
  walk). It previously resolved from the client's working directory only, which for
  a stdio MCP client is arbitrary, so it answered from the wrong instance.
- `plane drift` now catches a dead reconcile heartbeat. The `launchd`/`systemd`
  adapters set the general `drifted` fact when a service whose own definition means it
  to run (a load-at-login or interval launchd agent, an installable systemd unit) is
  present on disk but not loaded/enabled, and `plane schedule` marks its entry
  `tolerance: alert`. Before, an agent that silently unloaded left drift green while the
  shell prompt kept showing stale state, the exact failure the ambient loop exists to
  prevent; `plane apply` already treated it as a change, so drift and apply now agree.

### Changed

- **BREAKING:** renamed the project and distribution from `tarmac` to `planeops`. The
  PyPI name `tarmac` was taken by an unrelated deployment tool, blocking a clean
  install; the MCP server's tools are now `planeops_observe`/`planeops_drift`. The CLI
  command is unchanged: it is still `plane` (and `plane-mcp`). Pre-launch, so no
  installed users are affected.

### Added

- `plane schedule`: set up the ambient reconcile as an OS-native timer (launchd on
  macOS, systemd on Linux) running `plane reconcile` at login and on an interval
  (`--every 6h` / `30m` / `90s`, `--no-login`, `--off`). It writes the timer files
  (with the current PATH baked in so scheduled adapters find their tools) and declares
  a `launchd`/`systemd` registry entry; `plane apply` loads it through the confirm gate
  and `plane drift` then governs the schedule itself. Scheduler backends live under
  `planeops/schedulers/<os>/` and are self-discovered per platform, no OS branch, the
  same package-scan pattern as adapters and platforms.
- The `systemd` adapter now observes and converges `.timer` units, not just
  `.service` (a unit is a unit: `UNIT_TYPES` is data, not a branch, so is-enabled/
  is-active and enable/disable apply uniformly). This is the Linux parity to a
  scheduled launchd plist, letting a scheduled job (a reconcile timer) be
  drift-governed; the prerequisite for `plane schedule` on Linux.
- MCP server: two pure-read tools, `planeops_status` (the last drift report without
  rescanning) and `planeops_mcp` (the cross-client MCP view), alongside the existing
  `planeops_observe`/`planeops_drift`. Both annotated read-only + idempotent; the
  server still exposes no mutation tool.
- `plane reconcile`: `observe` then `drift` in one pass (exit 2 on alerts), the single
  command a scheduler runs for the ambient loop, so drift stays current without a
  hand-written shell wrapper gluing the two verbs together.
- `plane import <kind> --write` lands the proposal into `registry/imported.yaml`
  (merged + de-duped by id, into a file separate from hand-curated ones), so
  onboarding is `plane observe && plane import observed --write` (seed the registry
  from the machine, then prune) instead of hand-copying YAML. Prints and confirms
  first; `--yes` skips the prompt for scripts. Never writes without a readable stdin
  or `--yes`.
- `plane init [path]`: the one-command on-ramp. Scaffolds an instance (a `.planeops`
  marker, `registry/`, and the commented reference `instance.yaml`) and writes
  `~/.config/planeops/config.toml` pointing at it, so the installed `plane` finds it
  from any directory. The reference `instance.yaml` now ships as package data
  (`planeops/instance.example.yaml`), so an installed user gets the full documented
  template, not just a stub. Idempotent; keeps existing files, repoints only with
  `--force`. `--seed` then observes the machine and seeds the registry in the same
  command (`--no-seed` scaffolds only; interactive runs offer it, default yes), so
  `plane init <path> --seed` lands a governed registry to prune in one step.
- Instance resolution: `plane` locates the instance by precedence, `--repo` >
  `$PLANEOPS_INSTANCE` > `~/.config/planeops/config.toml` (honoring `$XDG_CONFIG_HOME`)
  > the current directory walking up to a `.planeops` marker.
- `plane mcp`: a read-only cross-client view of MCP servers from the last snapshot.
  Lists each server and the clients it is wired into, and flags servers wired into
  only one client (reuse candidates), the same tool under different names across
  clients (naming drift), and servers observed but absent from the registry
  (ungoverned). `--json` emits the structured view. Pure read with the same
  no-recompute posture as `plane status`; reads what `plane observe` already wrote,
  never scans the machine. This is the observability half of MCP management; wiring
  servers across clients (converge) stays deferred behind `plane apply`.
- Optional read-only MCP server (`plane-mcp`, install with the `mcp` extra) exposing
  two tools, `planeops_observe` (inventory the machine) and `planeops_drift` (structured
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
  planeops governs it as one domain.
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

[Unreleased]: https://github.com/albertorsesc/planeops/commits/main
