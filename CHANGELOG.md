# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project aims
to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- The re-auth checklist clears as it is worked: an interactive credential
  whose observation reports configured drops off, instead of every
  interactive credential standing on the list forever. Unconfigured and
  unobserved (adapter unbuilt) credentials keep their line.
- `plane secrets add`/`remove` end with the `plane observe` hint, so the
  snapshot-staleness step is guided instead of discovered.

## [0.6.0] - 2026-08-07

### Added

- A designed terminal experience behind a presentation port
  (`planeops/providers/ui`; the fitness test bans drawing imports anywhere
  else). `plane drift` renders its triage inline: a state headline, then
  alert/report/ungoverned/re-auth sections with aligned ids, symbols
  carrying state so color is never load-bearing, shared messages stated
  once, big sections truncated to the file. `plane observe` answers with a
  per-adapter breakdown, `plane status` in two calm lines, `plane mcp` as a
  bordered table with one client per line, and `plane apply` frames each
  diff in the tool's only panel. Styling appears only on a terminal: piped
  output stays plain, `NO_COLOR` is respected, `--json` and `--short` are
  byte-untouched.
- Every `--help` page is styled and every verb carries a full description,
  so the CLI documents itself.

### Changed

- Runtime dependencies grow from one to three: `rich` and `rich-argparse`
  join `ruamel.yaml`, both confined to the presentation leaf.

## [0.5.0] - 2026-08-07

### Added

- The mcp adapter reads a known client's extra wiring scopes from the
  client's own config: for claude-code, each `projects.<dir>.mcpServers`
  section and each committed `.mcp.json` in those directories. Scoped
  wirings observe under `<client> project:<dir>` / `<client> repo:<dir>`
  labels, so a server wired only inside one project is visible and
  governable instead of silently absent. A client declares its scopes via
  the new optional `scopes` reader on the clients seam.

## [0.4.0] - 2026-08-07

### Added

- `plane secrets list` (names only, never values) and `plane secrets remove
  <name>` (behind a confirm; the store is untouched on any failure). Store
  kinds opt in via the `EnumeratesKeys` and `RemovesValues` protocols.
- `planeops_secrets_list` on the MCP server: the same names-only read for
  assistants, without paying for a full scan. Mutations stay CLI-only.
- A store key that no registry entry declares now appears in the snapshot and
  lands in `plane drift` as ungoverned, the same way an undeclared service
  does. Requires a store kind that can enumerate names; presence facts and
  the "required secret is not configured" alert are unchanged.

## [0.3.0] - 2026-08-04

### Changed

- `plane secrets add` on a machine with no store offers the store's own
  bootstrap inline (previewed and confirmed, `--age-key` supported) instead of
  failing and pointing at `plane secrets init`. The standalone `init` remains
  for pre-provisioning. A store kind opts in by exposing `ready()` on the
  `AcceptsValues` protocol.

## [0.2.0] - 2026-08-03

### Added

- `plane secrets add <name>`: put one value into the store safely. Prompted
  twice blind on a terminal (or piped with `--yes` for scripting); the value
  never appears on a command line, in the environment, or in any output.
  Rotating an existing value requires `--force`. Store-side, the write goes
  through a transient owner-only file beside the store, is verified encrypted
  before it atomically replaces the store, and is zeroed on every path out.
  A store kind opts in via the `AcceptsValues` protocol.

### Changed

- README restructured around a plain-language purpose statement and one-line
  feature bullets; the instance, secrets, and MCP deep-dives moved to
  `docs/instance.md`, `docs/secrets.md`, and `docs/mcp.md`. Corrects the
  runtime-dependency name (ruamel.yaml) and the discovery-seam count.

## [0.1.0] - 2026-08-02

### Changed

- **BREAKING (pre-1.0):** the YAML dependency is `ruamel.yaml` (was PyYAML),
  introduced behind a new third-party ring: `planeops/providers/yaml` is the
  port every load/dump goes through, the vendor lives in one leaf module, and
  an architecture fitness test fails any third-party import outside its
  sanctioned home. Chosen for round-trip editing: planeops modifies files
  humans own and comment, and hand-rolled text surgery for that was a
  recurring bug class. Dependency count stays at one.

- **BREAKING (pre-1.0):** a secrets ref is `secret://<name>`: one name segment,
  strict charset. The old `secret://<store>/<name>` form bound a store kind into
  every consuming entry while the segment was never read by any code; which
  store serves a ref is instance configuration (`secrets.store`), so swapping
  stores touches zero entries. The old form fails at load with the rewritten
  ref spelled out.
- **BREAKING (pre-1.0):** a store's own settings nest under its name in
  `instance.yaml` (`secrets: {store: sops, sops: {path: ...}}`), so engine keys
  (`store`, `allow_targets`) and provider keys can never collide; a provider
  sees only its own sub-mapping. The old flat `secrets.path` fails loudly with
  the new shape spelled out, and an unknown key in the `secrets:` section is a
  load error like any other typo.
- The value-capable secrets handle goes only to the adapter registered under
  the reserved name `secrets`; a domain string is adapter-declared and open, so
  declaring `secret` grants nothing. Implementation names across every seam
  must match `[a-z0-9_.-]+` (a slash would corrupt `<adapter>/<native_id>`
  keys), and the `Platform` contract now declares `sys_platforms` instead of
  selection silently defaulting an undeclared attribute. All three close gaps
  that would have become breaking contract changes once third-party adapters
  exist.
- **BREAKING:** renamed the project and distribution from `tarmac` to `planeops`. The
  PyPI name `tarmac` was taken by an unrelated deployment tool, blocking a clean
  install; the MCP server's tools are now `planeops_observe`/`planeops_drift`. The CLI
  command is unchanged: it is still `plane` (and `plane-mcp`). Pre-launch, so no
  installed users are affected.
- **BREAKING (pre-1.0):** the sops store's default location moved from
  `registry/secrets.sops.yaml` to `secrets.sops.yaml` at the instance root, and
  `registry/` now holds only registry documents (`entries:` / `globs:`). The
  old cohabitation only worked because unknown top-level keys were silently
  skipped; now that they are rejected, a store parked in `registry/` fails
  loudly at load. Migration: move the file to the instance root (or point
  `secrets.path` at its new home).
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

- **BREAKING (pre-1.0):** `plane init` without a path ASKS where to create the
  instance (suggested default `~/planeops`; any valid path is accepted,
  hidden or nested included; `--yes` accepts the default non-interactively)
  instead of silently claiming the current directory. Nothing is ever placed
  unasked, the same confirm posture as every other write.

- Registry files the tool writes read like documents: one blank line between
  entries (`import --write`, `schedule`), and a re-import appends only NEW
  entries as text, so comments and pruning marks a user adds to
  `registry/imported.yaml` survive instead of being re-dumped away. Output
  paths are anchored (`-> <instance>/observed/<host>/...`), `plane status`
  names the instance that answered, and `--help` lists verbs in journey order
  (`init` first).

### Added

- Known-client conventions are DERIVED at read time, never copied into
  config: a source labeled as a discovered client inherits that client's log
  template unless `instance.yaml` overrides it. Tool upgrades reach existing
  instances through plain `observe` with no config edit, no `--update` verb,
  and no write: observe stays read-only.
- `plane mcp init`: detects known clients on this machine (claude-code,
  claude-desktop, codex, cursor) and wires them as `mcp.sources`, including
  the desktop's per-server log template, with the standard preview-and-confirm.
  The client-conventions table lives in the mcp adapter (extensions may know
  vendors; the core still cannot), and the write is a round-trip edit of
  `instance.yaml`: your comments, order, and formatting survive.

- `mcp.sources` reads TOML configs too (`format: toml`, stdlib parser), so
  codex-style `[mcp_servers.<name>]` tables are first-class sources; an
  unknown format is a load error instead of being silently parsed as JSON.
- Log locations are observed, not hand-hunted: the `launchd` adapter reads a
  plist's own `StandardOutPath`/`StandardErrorPath`, the `systemd` adapter
  reports the unit's `journalctl` invocation, and an `mcp` source may declare
  a per-server log template (`logs: .../mcp-{name}.log` in `instance.yaml`;
  client knowledge stays instance data, never adapter code). Seeding copies
  observed log locations into each proposed entry's `logs:`, so a fresh
  manifest knows where everything writes from day one.
- `plane secrets init`: the tool bootstraps its own store (age identity if
  missing, the instance's creation rules, an empty encrypted store), with the
  standard preview-and-confirm. Every underlying sops call passes `--config`
  explicitly and the identity is created where sops itself looks on this OS,
  so no command depends on the working directory and no environment variable
  is needed for a fresh setup. A store kind opts in via the `BootstrapsStore`
  protocol; re-initializing over an existing store is refused. (A cwd-sensitive
  manual `sops -e` could leave a store in plaintext; this removes the manual
  step entirely.)
- Entries can record where their asset logs (`logs:` list of paths or
  commands); `plane schedule` fills it in for the reconcile job it declares.

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

### Fixed

- An npm global installed without a version (a linked or broken package) is
  observed with an unknown version instead of being silently dropped from the
  snapshot, which made such a package invisible.


- A store file that is NOT actually encrypted (a failed `sops -e` leaves
  plaintext behind) is refused loudly as a failed scan with the fix spelled
  out, instead of presence blessing cleartext with `configured: true` and
  zero alerts. The decrypt-failure hint about `SOPS_AGE_KEY_FILE` appends
  only on identity-shaped failures. `parked` now means keep-as-is in both
  service adapters: a parked unit is never bootstrapped or booted out, so a
  freshly seeded registry plans nothing. Every output path is
  instance-anchored (apply and reconcile had two remaining bare
  `observed/...` lines; a fitness test now bans the pattern).
- Seeding describes the machine instead of proposing changes to it: an asset
  on disk but not active (an unloaded agent, a disabled unit) seeds as
  `parked`, so `plane apply` on a fresh registry no longer offers to bootstrap
  things the user never chose (such as a swept-in vendor updater).
  `plane schedule`'s hint names the exact `plane apply --id ...` command. The
  sops decrypt error keeps the actionable tail of stderr and names
  `SOPS_AGE_KEY_FILE`. The scaffolded `mcp.sources` example is commented out
  instead of shipping live placeholder paths.
- The sdist is an explicit allowlist. The default selection packed anything the
  repo `.gitignore` missed, including untracked local tooling state on the
  build machine; now only the intended tree ships.
- `mcp.sources` items are fully strict: an unknown field (`kye:`) and a
  non-string `key` are load errors like every other typo, and a source FILE
  that exists but cannot be parsed surfaces as a failed scan instead of
  quietly observing no servers (an absent file stays quiet: the tool may
  simply not be installed).
- A reachability failure of `systemctl --user` while user units exist on disk
  is a failed-scan alert naming the likely fix (`XDG_RUNTIME_DIR`), instead of
  silently observing zero units; an absent `systemctl` (macOS) stays quiet.
  `plane schedule` only claims "the new job is in the snapshot" when it
  actually is, and warns otherwise. The `plane-mcp` missing-extra hint no
  longer assumes pip. Count messages pluralize ("wrote 1 entry").
- A directory without the `.planeops` marker is refused by every verb (and by
  the MCP server's tools) with "run `plane init <path>` first", instead of
  being adopted with a warning and having `observed/` state scattered into
  whatever directory the command ran from. Only `plane init` creates
  instances.
- `plane-mcp` on an install without the `mcp` extra prints
  "pip install 'planeops[mcp]'" and exits 1 instead of a raw import traceback.
- `injected_as` on a secrets item must be `file:<path>#KEY`. The `env:NAME`
  form the old error message advertised was silently dropped at
  materialization; it is now rejected at load as not yet supported, and a
  typo'd key inside a secrets item (`injectd_as:`) fails like any other
  unknown key instead of quietly meaning "never materialize this secret".
- A typo'd YAML key is a loud error, never a silent no-op. Unknown keys on a
  registry entry (`tolerence:`, `need:`), on a top-level registry document
  (`entrys:`), and malformed items in `mcp.sources` (`pth:`) are rejected with
  a did-you-mean suggestion, or the allowed key set when nothing is close.
  Previously each was silently ignored, so the escalation, the whole file, or
  the entire source list quietly contributed nothing. `id`/`adapter`/`domain`/
  `intent` must be strings, `hosts` a non-empty list of non-empty strings, and
  a glob's value a non-empty string, all enforced at load with the entry named.
- `phase` must be an integer and `pin` a string at registry load (a YAML
  `phase: "3"` used to load fine and then crash apply's phase sort). Every verb
  notes a resolution landing on a directory without the `.planeops` marker (the
  skipped-init trap), and `plane schedule` warns when the plane binary it bakes
  into the job does not exist yet.
- Hardening follow-ups: parents created for a materialized secret
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

[Unreleased]: https://github.com/albertorsesc/planeops/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/albertorsesc/planeops/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/albertorsesc/planeops/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/albertorsesc/planeops/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/albertorsesc/planeops/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/albertorsesc/planeops/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/albertorsesc/planeops/releases/tag/v0.1.0
