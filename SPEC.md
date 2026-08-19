# SPEC v0.1: authoritative build specification

Status: current-state spec, kept in lockstep with the code. Where this file and
the implementation disagree, one of them is a bug to fix in the same change.
This file is the authoritative record of the design; it wins over any other
design note.

Date: 2026-07-31.

## 1. Locked decisions

| Decision | Choice | Rationale |
|---|---|---|
| Repo shape | Public engine repo (this repo: engine, spec, example registry, tests); machine-specific data (real registry, snapshots, secrets) lives in a separate private instance | planeops/instance split |
| Language | Python >= 3.12, uv-managed, `src`-less flat `planeops/` package, pytest | Matches the target machine's tooling; the workload is subprocess-bound, so a systems language buys nothing (evaluated 2026-07) |
| CLI | `plane` entry point; verbs: `init`, `observe`, `drift`, `status`, `reconcile`, `schedule`, `mcp`, `apply`, `import` | `cp` collides with coreutils |
| Secrets | sops+age file in-repo is primary; env files are materialization targets; age private key travels out-of-band | portable across machines; values never in-repo |
| Reconciler | Human. No code path mutates the machine without a rendered plan and an explicit confirmation (`apply` per change; `schedule` and `import --write` per run, with `--yes` for scripts); the scheduled job runs `reconcile` (observe+drift) only | no unattended mutation |
| Daemons | None, ever. The optional `plane-mcp` server is a user-started stdio process with no listening port; it never mutates the managed machine (its one non-pure tool refreshes the recorded snapshot) | smallest attack surface |
| Adapter wire | In-process Python protocol (section 4); adapters are packages under `planeops/adapters/`, discovered by package scan, never by a central edit list. The same discovery pattern governs importers, platforms, schedulers, and secrets stores (selected by `secrets.store`, defaulting to the provider that declares itself default) | OCP: add or swap one without editing the core |
| Formats | `registry/` = YAML (human-authored, any file grouping); `observed/<host>/snapshot.json` = generated JSON; `observed/<host>/DRIFT.md` + `DRIFT.json` = generated report panes | desired state authored, observed state generated |
| Non-goals | planeops is not an agent runtime, orchestrator, or gateway: it never sits in any request path and never proxies traffic. Windows support is deliberately out of scope until real demand exists (the platform seam accepts it structurally; every adapter currently assumes POSIX tools). Statistical/ML anomaly scoring stays out of the core | the invariants ARE the product |
| Rent/usage | Optional capability, not v0.1 scope | deferred |

## 2. Entry schema (field reference)

One entry = one managed asset. Registry files contain `entries: [...]`.

| Field | Type | Req | Default | Notes |
|---|---|---|---|---|
| `id` | str | yes | | Unique. Convention `<adapter>/<native-id>`, e.g. `launchd/com.example.agent-gateway`, `ollama/qwen3:30b` |
| `adapter` | str | yes | | Owning adapter name |
| `domain` | str | yes | | Adapter-declared, open set: `service`, `model`, `package`, `mcp-server`, `config`, ... |
| `class` | enum | no | `recipe` | `recipe` \| `data` \| `cache`. `data` entries reproduce via their declared sync; `cache` normally appears only in `unmanaged` |
| `scope` | str | no | `machine` | `machine` \| `user` \| `project:<abs-path>` |
| `hosts` | list[str] | no | `[any]` | Pin to named hosts; observed state is always per-host |
| `lifecycle` | enum | yes | | `active` \| `maintain` \| `parked` \| `retired` \| `purge` |
| `owner` | enum | no | `runtime` | `plane` \| `runtime` \| `human` (a `human` entry is observed and reported, never written) |
| `tolerance` | enum | no | `report` | `auto` \| `report` \| `alert`; routes the soft drift signals (staleness, content drift, in-major version drift). Structural violations alert regardless |
| `intent` | str | yes | | One line: why this exists |
| `kill_criteria` | str | no | | Falsifiable where possible |
| `auth` | enum | no | `none` | `interactive` entries feed the re-auth checklist |
| `phase` | int | no | adapter default | Converge ordering (section 5) |
| `pin` | str | no | | Exact version pin. Only pinned entries get version-drift triage (same-major drift is tolerance-routed); with no pin, versions are recorded but not compared |
| `needs` | list[str] | no | `[]` | Ids of entries this one depends on; drift alerts when an active entry's dependency is retired/purged or absent |
| `logs` | list | no | `[]` | Where this asset writes its logs: file paths or a command that shows them (e.g. a `journalctl` invocation). Descriptive today; the time-axis work will read them |
| `secrets` | list | no | `[]` | Items: `{ref: secret://<name>, injected_as: file:<path>#KEY}`; which store serves a ref is instance config (`secrets.store`), never part of the ref. Validated at registry load; `env:NAME` is rejected as not yet supported, and unknown item keys are rejected like any other typo |
| `desired` | map | no | `{}` | Adapter-specific shape |
| `data` | map | `class: data` only | | `{location: <path>, sync: git \| none \| <backend>}` |

`registry/unmanaged.yaml` holds the two ways to say "not mine to govern":
`globs: [{glob: <pattern>, reason: <str>}]` matches an observation's name, and
`publishers: [{publisher: <identity>, reason: <str>}]` matches the identity its
adapter attested (`facts["publisher"]`; the `launchd` adapter reports the Team
ID its program is signed with). Attestation is per observation, not per adapter:
an agent that declares no program has nothing to sign, so it matches no
publisher rule and still needs a glob or a declaration. Either withholds the report's question, never the observation: matching
items are recorded in the snapshot (`unmanaged`, section 4) and skipped when
diffing, so the triage still sees them and a later pass can still report on the
exemption itself.

Three bounds follow. A rule never exempts a **declared** entry, because the
declaration is the more specific statement and dropping its evidence would
report an installed asset as missing. A rule covers an **always-on**
observation (section 5) only when its authority is something the subject cannot
choose for itself: an attested publisher, or a glob naming one asset exactly. A
glob carrying a metacharacter (`*?[`) claims a name space instead, and a name
space is one anything can enter by naming itself, so it never covers a
login-run service. And `plane import observed` proposes an exempted item
exactly when the report still asks about it. Section 2's lifecycle model plus
these rules define what "governed" means.

## 3. Repo layout

```
planeops/
├── SPEC.md
├── planeops/                   # Python package: core loop, schema, report, contracts
│   ├── core/                 # vendor-free: schema, observe, drift triage, apply, report, locate, statefile
│   ├── adapters/             # one package per adapter (scan-discovered)
│   ├── importers/            # one module per import kind (scan-discovered)
│   ├── platform/             # one module per OS (scan-discovered): darwin, linux
│   ├── schedulers/           # one package per OS scheduler backend (scan-discovered)
│   ├── secrets/              # store contracts, redaction gate, resolve; stores/ per kind (scan-discovered)
│   └── mcp_server/           # optional read-only MCP server (mcp extra)
├── registry/                 # example entries + unmanaged.yaml
├── observed/<host>/          # snapshot.json + DRIFT.md + DRIFT.json + applied.jsonl (generated)
├── tests/                    # mirrors planeops/ one-to-one
└── pyproject.toml            # uv-managed; console scripts `plane`, `plane-mcp`
```

## 4. Contracts (Python protocols)

```python
class Adapter(Protocol):
    name: str
    domains: tuple[str, ...]
    def observe(self, ctx: Ctx) -> list[Observed]: ...   # required, read-only

class MutatingAdapter(Adapter, Protocol):                # opted into by implementing it
    def plan(self, entry: Entry, obs: Observed | None, ctx: Ctx) -> list[Change]: ...
    def execute(self, change: Change, ctx: Ctx) -> Result: ...  # post-confirmation only
```

Optional adapter class data (not part of the protocol; read via `getattr`):
`default_phase: int` (converge order, section 5) and `EXECUTE_TIMEOUT: float | None`
(per-operation subprocess ceiling: `None` for confirmed long operations like
installs and model pulls, bounded for service/config operations).

Core wire types:

```python
Observed = {adapter: str, native_id: str, facts: dict, version: str | None}
# matches an Entry when f"{adapter}/{native_id}" == entry.id
Change   = {entry_id: str, kind: "install" | "configure" | "remove" | "patch",
            diff: str,            # human-readable, shown at confirmation
            action: dict}         # adapter-opaque execute payload
Result   = {ok: bool, detail: str}
# snapshot.json = {host, ts, schema_version, engine_version,
#                  observed: [Observed], unmanaged: [{key, glob} | {key,
#                  publisher}] (which observations a rule exempts, and which
#                  rule answered for each),
#                  uncovered: [adapter names declared in registry but not
#                  implemented], failed: [{adapter, error}]}
```

- Engine, not adapters, owns confirmation: `plan()` proposes `Change`s;
  `execute()` runs one confirmed change. An adapter without `plan`/`execute` is
  observe-only.
- `ctx` is required on `plan`: the engine always provides it (an optional-`None`
  contract only invited None-guards for a state production never produces).
- General facts the triage understands from ANY adapter: `present` (semantic
  presence, e.g. a service is present when loaded/enabled, not when its file
  exists; absent fact means observed-at-all is presence, and `present: False`
  on an active/maintain entry is the same structural alert as observing
  nothing at all), `drifted` (content or
  definition drift, tolerance-routed), `always_on` (will run code at login/on a
  schedule; drives the ungoverned alert), `stale` (attestation age),
  `configured` (secret presence), and `governed_by` (the id of a declared
  entry this observation is evidence for; skips the ungoverned pass while
  that entry exists, falls back to visible when it is deleted).
- An adapter states those six through `Observed.of`, which names them as
  keyword arguments, so a misspelling is an unexpected argument the type
  checker reports at the line that wrote it. Its `detail=` carries everything
  else the domain records, untouched. An unset argument writes no fact, which
  is the domain having no opinion; `present=False` is the domain saying no.
- Observe re-checks the six as it collects them, because an adapter is a
  discovery seam and third-party ones are never type-checked here. A general
  name written with different case or separators (`alwayson`, `always-on`), or
  a general fact carrying the wrong type, fails that adapter's scan into
  `failed` with the reason. The rule is exact rather than approximate, so
  `present_at` and `configured_by` stay ordinary domain facts: the map is open,
  and only the vocabulary the triage acts on is fixed.
- `Ctx.secrets` carries the redaction gate: a presence-only handle whose
  `get()` raises everywhere except inside the secrets adapter's confirmed
  execute, where the engine substitutes a value-capable handle it builds from
  the backend.
- The `manual` adapter ships in core: observe = attestation recorded in observed
  state, no execute. Attestations refresh only in an interactive
  `plane observe --attest`; in scheduled runs the last attestation is reused and
  marks stale after 30 days (report-level drift). `manual` is reserved for
  assets with no planned adapter; rows whose real adapter is merely unbuilt keep
  the real adapter name and surface under **Uncovered**.
- Shared subprocess seam (`planeops/_run.py`): every shell-out goes through one
  injected `Runner` with a per-call timeout; a timeout (exit 124, "may still be
  running") is distinct from a missing binary (127).

## 5. Verbs, exit codes, and phases

- `plane init [path]` scaffolds an instance (marker, `registry/`, commented
  `instance.yaml`) and registers it in `~/.config/planeops/config.toml`;
  `--seed` observes and seeds the registry in the same run.
- `plane observe [--attest]` writes `observed/<host>/snapshot.json`. Read-only.
  A crashed adapter is contained, recorded under `failed`, and warned about.
- Every drift item carries its entry's `intent`, and `kill_criteria` where set,
  so the reason a thing was declared is read where the problem is. An item the
  ungoverned pass built from an observation has no declaration behind it and
  carries neither.
- `plane drift` renders `DRIFT.md` + `DRIFT.json`: **Alerts** (lifecycle
  violations, missing required secrets, failed adapter scans, ungoverned
  always-on services, broken `needs` dependencies), **Report**, **Auto-folded**
  (tolerance-routed soft drift), **Uncovered** (entries awaiting their adapter),
  **Ungoverned** (observed, neither declared nor unmanaged), **Re-auth pending**.
  `--json` prints the same structured report.
- `plane status [--short|--json]` reads the last `DRIFT.json` without
  recomputing; `--short` is the shell-prompt token (silent when clean).
- `plane reconcile` = observe + drift in one pass; what the OS timer runs.
- `plane schedule [--every 6h] [--no-login] [--off] [--yes]` previews and (after
  confirmation) writes the OS-native reconcile timer + a governed registry
  entry, then observes; `plane apply` loads it. Backends under
  `planeops/schedulers/<os>/`, scan-discovered.
- `plane mcp [--json]` is the read-only cross-client MCP view.
- `plane apply [--id <id> | --phase <n>]` plans, renders each change, confirms
  per change (`y`/`n`/`a` = rest of domain), executes, journals each record the
  moment it is decided (`applied.jsonl`), re-observes AND recomputes the drift
  panes. An unknown `--id` is a loud error. "No changes planned" reports any
  standing alerts instead of claiming the machine matches.
- `plane import <kind> [path] [--adapter <n>] [--write] [--yes]` proposes
  registry entries; `observed` defaults its path to the host's own snapshot.
- Exit codes, uniform: `0` ok, `1` operator error (bad registry, missing/torn
  snapshot, unknown id, unsupported platform: handled once at the CLI dispatch
  point) or a confirmed change that failed during `apply`, `2` drift alerts
  exist (`drift`, `status`, `reconcile`). `--json` always emits JSON on stdout,
  an `{"error": ...}` object when unseeded or on an operator error.
- Converge phases (encoded as adapter `default_phase`, entry `phase` overrides):
  2 packages/CLIs (`pkg-brew`, `pkg-npm`, `pkg-uv`) → 3 config (`chezmoi`) →
  4 models (`ollama`) → 5 secrets materialization → 6 services (`launchd`,
  `systemd`: load last, against complete config). Unphased entries converge
  after phased ones.

## 6. Manifest import mapping

The section-to-adapter mapping is configuration, not code: rules live under
`instance.yaml`'s `importer.rules` at the instance root
(`planeops/instance.example.yaml` ships as the template) and the importer names no
specific tool. A section matching no rule imports as `manual`. Import kinds are
scan-discovered (`stackfile`, `envfile`, `observed`); every imported row carries
an intent marking it for human verification, and `--write` lands proposals in
`registry/imported.yaml` (de-duped, confirmed) for pruning.

## 7. Testing

- Unit: each adapter tested against fixture outputs of its tool; no unit test
  touches the live machine.
- Contract conformance: a shared parametrized suite every discovered adapter
  must pass; the suite fails the build if a discovered adapter is not covered.
- Engine: schema validation, triage, redaction gate (tests prove `secrets.get`
  raises during observe and that a leaking adapter fails rather than leaks).
- Integration: real tools (sops/age/chezmoi on both CI OSes, systemctl on the
  Linux job, launchctl on the macOS job). The Linux job's release-binary
  downloads are version-pinned and checksum-verified; the macOS job installs
  through Homebrew (its own trust channel).
- `tests/` mirrors `planeops/` one-to-one.

## 8. Milestones

- **M1-M4 (done)**: engine core; package + launchd adapters with plan/execute;
  ollama + mcp + chezmoi (config reproduction delegated to chezmoi rather than a
  tool-specific config engine); systemd parity incl. `.timer` units; secrets
  (sops+age store, materialization, redaction gate, containment); onboarding
  (`init --seed`, instance resolution, `import observed --write`); the ambient
  loop (`reconcile`, `schedule`, dead-heartbeat detection); shadow detection
  (ungoverned + always-on alerts); structured `DRIFT.json`; `status`; `mcp`
  view; the optional read-only MCP server.
- **Next**: a tagged, installable release with signed artifacts, then the
  holistic clean-account reproduction rehearsal as the end-to-end acceptance
  test. The forward roadmap (adapter surfaces, transitions journal, reproduce,
  multi-host) is tracked outside this spec.
- Post-v0.1 (explicitly out): usage/rent, policy compilers, docker adapter,
  agent-runtime anything (see Non-goals).
