# SPEC v0.1: authoritative build specification

Status: current-state spec. It is distilled from a private design evidence trail kept outside this public repo; **where that trail conflicts with this file, this file wins.** Three known conflicts resolved here: secrets default is sops+age (not Keychain); the build order lands the launchd adapter in M2 ahead of the harness-config adapter, because the first two real transactions (a legacy gateway retirement, updater relocation) are launchd-shaped; and converge materializes secrets before loading services, so services start against complete config.

Date: 2026-07-22.

## 1. Locked decisions

| Decision | Choice | Rationale trail |
|---|---|---|
| Repo shape | Public engine repo (this repo: engine, spec, example registry, tests); machine-specific data (real registry, snapshots, secrets) lives in a separate private instance | engine/instance split |
| Language | Python >= 3.12, uv-managed, `src`-less flat `engine/` package, pytest | Matches the target machine's tooling (uv present) |
| CLI | `plane` entry point (`uv run plane <verb>`); verbs: `observe`, `drift`, `apply`, `import` | `cp` collides with coreutils |
| Secrets | sops+age file in-repo is primary; Keychain and env files are materialization targets; age private key travels out-of-band | portable across machines; values never in-repo |
| Reconciler | Human. Engine has no code path that mutates the machine without rendering a change and receiving confirmation; the scheduled job may run `observe` + `drift` only | no unattended mutation |
| Daemons | None, ever | smallest attack surface |
| Adapter wire | In-process Python protocol (section 4); adapters are packages under `engine/adapters/`, discovered by package scan, never by a central edit list | OCP: add an adapter without editing the core |
| Formats | `registry/` = YAML (human-authored, any file grouping); `observed/<host>/snapshot.json` = generated JSON; `observed/<host>/DRIFT.md` = generated report | desired state authored, observed state generated |
| Rent/usage | Optional capability, not v0.1 scope | deferred |

## 2. Entry schema (field reference)

One entry = one managed asset. Registry files contain `entries: [...]`.

| Field | Type | Req | Default | Notes |
|---|---|---|---|---|
| `id` | str | yes | | Unique. Convention `<adapter>/<native-id>`, e.g. `launchd/ai.example.gateway`, `ollama/qwen3:30b` |
| `adapter` | str | yes | | Owning adapter name |
| `domain` | str | yes | | Adapter-declared, open set: `service`, `model`, `package`, `mcp-server`, `skill`, ... |
| `class` | enum | no | `recipe` | `recipe` \| `data` \| `cache`. `data` entries reproduce via their declared sync; `cache` normally appears only in `unmanaged` |
| `scope` | str | no | `machine` | `machine` \| `user` \| `project:<abs-path>` |
| `hosts` | list[str] | no | `[any]` | Pin to named hosts; observed state is always per-host |
| `lifecycle` | enum | yes | | `active` \| `maintain` \| `parked` \| `retired` \| `purge` |
| `owner` | enum | file-backed only | `runtime` | `plane` \| `runtime` \| `human` (single-writer rule) |
| `tolerance` | enum | no | `report` | `auto` \| `report` \| `alert` |
| `intent` | str | yes | | One line: why this exists |
| `kill_criteria` | str | no | | Falsifiable where possible |
| `auth` | enum | no | `none` | `interactive` entries feed the re-auth checklist |
| `phase` | int | no | adapter default | Converge ordering (section 5) |
| `pin` | str | no | | Exact version pin; absent = recorded-or-newer-within-major |
| `secrets` | list | no | `[]` | Items: `{ref: secret://<backend>/<name>, injected_as: env:NAME \| file:<path>#KEY, rotation: <dur>}` |
| `desired` | map | no | `{}` | Adapter-specific shape (e.g. `{present: true}`, launchd plist source path, model tag) |
| `data` | map | `class: data` only | | `{location: <path>, sync: git \| none \| <backend>}` (sync backend is adapter-declared, not a core enum) |

`registry/unmanaged.yaml`: `globs: [{glob: <pattern>, reason: <str>}]`. Observed items matching a glob are skipped before diffing.

## 3. Repo layout (v0.1)

```
planeops/
├── SPEC.md
├── engine/                   # Python package: core loop, schema, report, contracts
│   ├── core/                 # vendor-free: schema, drift triage, rendering, confirm loop
│   ├── adapters/             # one package per adapter (scan-discovered)
│   ├── platform/darwin.py    # platform contract impl
│   └── secrets/              # backend contract + sops_age.py, keychain.py
├── registry/                 # entries + unmanaged.yaml (+ secrets.sops.yaml encrypted)
├── policy/                   # deferred beyond secrets rotation classes
├── observed/<host>/          # snapshot.json + DRIFT.md (generated; commit is opt-in)
├── tests/                    # mirrors engine/ one-to-one
└── pyproject.toml            # uv-managed; console script `plane`
```

## 4. Contracts (Python protocols)

```python
class Adapter(Protocol):
    name: str
    domains: tuple[str, ...]
    default_phase: int
    def observe(self, ctx: Ctx) -> list[Observed]: ...          # required, read-only
    def plan(self, entry: Entry, obs: Observed | None) -> list[Change]: ...  # recipe adapters
    def execute(self, change: Change, ctx: Ctx) -> Result: ...  # called only post-confirmation
    def usage(self, entry: Entry, ctx: Ctx) -> Usage | None: ...  # optional
```

This protocol splits `apply` into `plan` + `execute` so the engine owns confirmation; per-adapter `diff` is dropped (the engine computes structural diffs from `Observed`); `compile` is deferred post-v0.1 along with the policy compilers it serves.

Core wire types (M1 scope):

```python
Observed = {adapter: str, native_id: str, facts: dict, version: str | None}
# matches an Entry when f"{adapter}/{native_id}" == entry.id
Change   = {entry_id: str, kind: "install" | "configure" | "remove" | "patch",
            diff: str,            # human-readable, shown at confirmation
            action: dict}         # adapter-opaque execute payload
Result   = {ok: bool, detail: str}
Usage    = {last: datetime | None, count: int | None}
# snapshot.json = {host, ts, engine_version, observed: [Observed],
#                  uncovered: [adapter names declared in registry but not implemented]}
```

- Engine, not adapters, owns confirmation: `plan()` returns `Change` objects; `execute()` is invoked per confirmed change. An adapter with no `plan/execute` is observe-only (report coverage without apply).
- `Ctx` carries platform + secrets handles. `ctx.secrets.get()` raises outside `execute()` (and, post-v0.1, compile paths): the redaction guarantee, enforced in code.
- `SecretsBackend`: `exists(name)`, `meta(name) -> {created, rotated} | None`, `set(name)` (interactive), `get(name)` (gated as above).
- `PlatformDarwin`: scheduler (launchd load/unload/list), standard paths, process listing.
- A `manual` adapter ships in core: observe = attestation recorded in observed state, no execute. Attestation prompts run only in interactive `plane observe --attest`; in non-TTY runs (the Sunday slot) `manual` reuses the last attestation and marks it stale after 30 days (stale attestation = report-level drift). `manual` is reserved for assets with no planned adapter; rows whose real adapter is merely unbuilt keep the real adapter name and surface under **Uncovered** until it lands.

## 5. Verbs and phases

- `plane observe` → writes `observed/<host>/snapshot.json`. Read-only, safe for the Sunday launchd slot.
- `plane drift` → renders `DRIFT.md`: **Alerts** (lifecycle violations, missing required secrets, new always-on services), **Report**, **Auto-folded** (in-major version drift), **Uncovered** (entries awaiting their adapter), **Re-auth pending**. Exit code 2 if alerts exist.
- `plane apply [--id <id> | --phase <n>]` → plan, render each change, confirm per change (`y`/`n`/`a` for rest-of-domain), execute, re-observe touched entries.
- `plane import stackfile <path>` → proposes registry entries (section 6); writes nothing without confirmation.
- Converge phases: 1 package managers/runtimes → 2 packages/CLIs → 3 harness config → 4 models → 5 secrets materialization → 6 services (load last, against complete config) → 7 re-auth checklist.

## 6. Manifest import mapping

The section-to-adapter mapping is configuration, not code: rules live under
`instance.yaml`'s `importer.rules` at the instance root (`engine/instance.example.yaml`
ships as a template) and the importer names no specific tool. A section matching no
rule imports as `manual`. The table below is an illustrative mapping; the `Skills`
row in particular is tool-specific and belongs in an instance's own config.

| manifest section | Adapter | Domain | Notes |
|---|---|---|---|
| Machine | `manual` | `host` | attestation only |
| Runtimes (Agent Execution) | `launchd` / `manual` | `service`, `harness` | services get real entries; harness binaries → package adapters where installable |
| Browser Automation | `pkg-npm` / `manual` | `package`, `app` | |
| Infrastructure | `manual` (docker adapter deferred) | `service` | observe-only in v0.1 |
| Custom Systems | `manual` | `project` | `class: data` pointers to repos + their sync |
| MCP Servers | `mcp` | `mcp-server` | reads a configurable source list (`instance.yaml`'s `mcp.sources`), merges servers by name across runtimes |
| Skills | `claude-code` | `skill` | recipe = source (repo/symlink target) |
| Secrets / API Keys / Subscriptions | `manual` (M1) → sops+age refs (M4) | `secret` | M1 imports names + `auth: interactive` flags as manual entries; M4's importer migrates them to `secret://` refs. Values never read |

Importer emission rule: a rule may name an adapter that is not yet implemented; such entries appear under DRIFT's **Uncovered** section, never as violations, and need no migration when the adapter lands. `manual` is the fallback for sections no rule matches. Every imported row carries `intent: "imported from manifest, verify"` for a human to confirm.

## 7. Testing

- Unit: each adapter tested against fixture outputs of its tool (recorded real output, then edited variants); no test touches the live machine.
- Contract conformance: one shared parametrized suite every adapter must pass (observe returns valid `Observed`, plan is pure, execute never runs unconfirmed).
- Engine: schema validation, triage, redaction gate (a test proves `secrets.get` raises during observe).
- Acceptance: the clean-account rehearsal, scoped per adapter during the build, full pass at milestone M4.
- `tests/` mirrors `engine/` one-to-one.

## 8. Milestones

- **M1**: engine core (schema, observe/drift loop, manual adapter, DRIFT rendering) + registry seeded via stackfile import. Machine fully covered, mostly by attestation.
- **M2**: pkg-brew, pkg-nvm (node runtime), pkg-npm, pkg-uv, launchd adapters with plan/execute. A machine's own scheduled maintenance script (e.g. a weekly stack updater) stays in that machine's private instance, out of any cloud-synced directory, and is governed here only as a `launchd` service entry, never committed to this repo. Its scheduled slot runs the update, then `plane observe && plane drift`, so every update lands already observed and drift-checked. (A legacy gateway retirement, originally this milestone's first transaction, was executed manually before the build.)
- **M3**: `ollama` adapter (done) and `mcp` adapter (done, cross-runtime MCP visibility from a configurable source list). Harness-config reproduction (`~/.claude` and any other tool's config) is delegated to an external, agnostic dotfiles manager (chezmoi) behind a normal adapter, rather than an in-house `claude-code` adapter, so no tool-specific config engine lives in the core.
- **M4**: secrets (sops+age store, importer, materialization, re-auth checklist) + a service home recipe (declared key-paths in its config, venv rebuild, cron jobs) + first full clean-account rehearsal green.
- Post-v0.1 (explicitly out): usage/rent, policy compilers, docker adapter, second host.
