# Contributing

Thanks for helping. This is the public engine repo; machine-specific data lives
in a separate private instance and never belongs here.

## Development setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/albertorsesc/planeops
cd planeops
uv sync
```

## The quality gate

Every change must pass all four checks. `make check` runs them (and `make test`
auto-fixes formatting first); CI runs the same ones on Python 3.12 and 3.13.

```bash
uv run ruff check planeops tests        # lint
uv run ruff format --check planeops tests  # formatting
uv run mypy                           # types (strict, planeops/)
uv run pytest                         # tests
```

`uv run ruff format planeops tests` applies formatting. Tests live in `tests/`,
mirroring `planeops/` one-to-one; a change ships with its tests.

## Writing an adapter

An adapter teaches the engine about one kind of asset. Adapters are discovered by
a package scan, so you never edit a central list.

1. Create a package under `planeops/adapters/<name>/`.
2. Implement the `Adapter` protocol from `planeops.core.contracts`: set `name` and
   `domains`, and implement `observe(ctx) -> list[Observed]` (read-only).
3. Expose the instance as a module-level `ADAPTER`. Discovery imports it and
   verifies it satisfies the contract.
4. To let the adapter converge its domain, also implement `MutatingAdapter`:
   `plan(entry, obs, ctx) -> list[Change]` (pure; `ctx` is always provided) and
   `execute(change, ctx) -> Result`. The engine renders each `Change` and takes
   a confirmation before calling `execute`; an adapter never mutates unprompted.
   Optionally declare `default_phase` (converge ordering; see SPEC section 5)
   and `EXECUTE_TIMEOUT` (`None` for confirmed long operations like installs,
   a bounded ceiling for quick service/config operations).
5. Add `tests/adapters/test_<name>.py` exercising `observe` (and `plan`)
   against recorded fixtures. No unit test touches the live machine; the shared
   conformance suite will fail until the new adapter is wired into it.

## Test layout (the mirror rule)

`tests/` shadows `planeops/` exactly, so knowing where code lives tells you where
its test lives:

- `planeops/<path>/<module>.py` -> `tests/<path>/test_<module>.py`.
- A package whose logic lives in `__init__.py` -> `tests/<path>/test_<package>.py`
  (e.g. `planeops/adapters/launchd/` -> `tests/adapters/test_launchd.py`).
- When a module grows several concerns, split the *implementation* into a
  package first (one module per concern) and mirror it, as `planeops/cli/` does
  with one module per verb; never let one test file become a junk drawer for a
  module that should be a package.
- Cross-cutting contract suites (`tests/core/test_conformance.py`,
  `tests/core/test_redaction.py`, and the tree-level
  `tests/test_architecture.py`, which enforces the layering rules and this very
  mirror rule in CI) sit beside what they enforce and are the sanctioned
  exceptions.
- Shared builders for one directory's tests live in that directory's
  `helpers.py` (e.g. `tests/cli/helpers.py`); fixtures go in `conftest.py`.
- `tests/integration/` is organized by scenario against real tools, a different
  axis than unit mirroring, deliberately.

## Design invariants

Hold these; a change that breaks one needs a very good reason:

- **No daemon, no open ports.** Every verb is a short-lived command.
- **Read by default.** Only `apply` writes, and only after a rendered diff and a
  per-change confirmation.
- **Secrets are references, never values.** No secret value enters the engine
  core, the repo, snapshots, or reports.
- **Provider-neutral.** No feature binds to a single vendor. Adapters shell out to
  local tools through the injected seam, with no network calls of their own.

## Commits, versioning, and PRs

Commits follow [Conventional Commits](https://www.conventionalcommits.org): a typed,
imperative subject under ~70 characters.

- Types: `feat`, `fix`, `docs`, `refactor`, `test`, `perf`, `chore`.
- A change that breaks the **registry schema, the CLI, the config format, or an
  adapter contract** is breaking: mark it `feat!:`/`fix!:` and add a `BREAKING CHANGE:`
  footer explaining the break and the migration.
- Add a body only when the reason isn't obvious from the diff; don't narrate tests.

Versioning is [SemVer](https://semver.org) with a [Keep a Changelog](https://keepachangelog.com)
`CHANGELOG.md`. Record user-facing changes under `Unreleased` in the right section
(`Added`/`Changed`/`Fixed`/`Deprecated`/`Removed`/`Security`), and prefix any breaking
entry with **BREAKING:**. Pre-1.0 (while `0.x`): a breaking change bumps the **minor**
(`0.MINOR.0`); features and fixes bump the **patch** (`0.x.PATCH`). After 1.0, standard
SemVer (breaking → major). One meaning carries through: the slot that moves is the one
that says "a contract moved", which is the minor until 1.0 and the major after it, so a
pin like `~=0.10.0` takes every fix and feature and stops exactly where reading is
required. Releases up to and including `0.10.0` bumped the minor for features too; from
`0.10.1` on, the minor is reserved for breaking changes as written here. CI enforces the
bump against the `Unreleased` sections, so the rule is checked rather than remembered.

The first published release is `0.1.0`, per the [SemVer FAQ](https://semver.org/#faq).
`1.0.0` is a stability commitment, deliberately deferred: it is cut when the registry
schema, the CLI, the config format, and the adapter contracts are stable enough that
other people's machines depend on them staying put, not at any feature milestone.

Open a PR against `main`; the template lists what to confirm, and the body should
state the change type and any breaking impact (and the version bump it implies).

## Running it without a human

Every verb that can change something asks first, and prompts read stdin like
any other program: a terminal answers, and so does a pipe (`printf 'y\n' |
plane apply`). An answer piped in is still an answer, and the diff is still
rendered, so nothing is bypassed.

Automation should say there is nobody to ask, by passing the verb's flag
(`--yes`, `--no-seed`) or by closing stdin (`plane init . </dev/null`). Both
take the conservative branch: decline the change, skip the seeding, refuse to
guess a path. Leaving stdin open with no answer coming blocks, exactly as any
program reading stdin does, and that is the one shape to avoid in a script.

`plane apply` has no `--yes` on purpose. Unattended convergence would undo the
one promise the tool makes, that nothing writes without a rendered diff and a
yes. Answering it from a pipe is possible and deliberately manual.

## Branching and releasing

`main` is the only long-lived branch. It stays green, it is always releasable, and
merging to it publishes nothing.

If you are not a maintainer, fork the repository, branch in your fork, and open
the pull request from there. That is the normal path and nothing below asks you
to have push access here. Two things surprise first-time contributors, and
neither is about your change: CI does not start until a maintainer approves the
run, and it needs approving again after each push, so a pending check usually
means it is waiting on a person. Coverage upload is also skipped for fork pull
requests, because GitHub does not issue the token it needs to a fork, by design.

Maintainers branch in this repository instead of forking, and the rest is the
same. Branches are named for their type (`feat/`, `fix/`, `docs/`, `ci/`,
`chore/`), one branch is one pull request, it is squash-merged, and the remote
branch is deleted on merge. Take one at a time; if something has to wait, push
the branch so the work is not only on your machine.

Squash merging means a local branch's tip never enters `main`'s history, so
`git branch -d` refuses it and `git branch --merged` never lists it. The state
worth looking for is the one auto-delete creates, an upstream that is gone:

```console
$ git fetch --prune
$ git branch -vv | grep ': gone]'   # each of these is safe to delete
```

There is no `develop` branch and there are no `release/` branches. An integration
branch exists to answer "is this collection of changes shippable", and the tag
already answers it: nothing reaches PyPI until a version is deliberately tagged,
so `main` carries no risk that a second branch would absorb.

### Publishing

Publishing is a deliberate act, never a side effect of merging.

1. Open a `chore(release):` PR that bumps `__version__` and moves the `Unreleased`
   entries into a new `## [X.Y.Z] - DATE` section.
2. Merge it.
3. Tag the merge commit and push the tag.

```console
$ git switch main && git pull
$ git tag -a vX.Y.Z -m "vX.Y.Z"
$ git push origin vX.Y.Z
```

Tags are annotated, so the object records who cut the release and when; a
lightweight tag is a bare pointer, and this one authorizes a publish. A pushed
`v*` tag can be neither moved nor deleted, by repository rule. If a tag is wrong,
the answer is a new version, never a repointed one.

The tag runs everything that can refuse before anything that cannot be undone:
the tagged commit must be on `main`, the full gate must pass against the tagged
tree, the tag must match `__version__`, the bump must agree with its changelog
section, and that section must exist. Only then does it build, publish through
Trusted Publishing, and create the GitHub Release from those same notes.

Publishing on a tag push rather than on a GitHub Release keeps the changelog as
the one source of the release notes. The cost is that a tag push is the last
human step before an irreversible one, which is why those checks run first.

### When a release is broken

Fix forward, then yank, and never delete from PyPI: a version number that has
been used can never be reused.

1. Land the fix on `main` and release it as the next patch.
2. Once the fix is published, yank the broken version, with a reason that names
   the symptom. That sentence is what pip prints to whoever lands on it.
3. Note the yank in that version's changelog section. The section stays; history
   is not rewritten.

Yanking is not deletion. The file is still served and an exact pin like
`planeops==0.10.3` still resolves to it with a warning, which is the point:
nobody who pinned exactly is broken, and nobody new arrives. It is a hint to the
resolver, so it is not on its own an answer to a security problem.

A maintenance branch is not part of this. Three things must be true at once
before one exists: a published `X.Y.Z` has a defect, someone is on that line and
cannot move off it, and `main`'s tip cannot be released as the fix because it
carries work that is not ready. Any two of those and the answer is still to fix
on `main` and release from `main`. When all three hold, the branch is cut from
the tag rather than from `main` (`git switch -c release/0.10 v0.10.2`), announced
in the changelog when it opens and when the line ends, and deleted then. Until
that day there is one supported line, and it is whatever `main` last released.

### What to expect

Fixes, documentation, and tests are welcome as a pull request directly. For a new
adapter, or anything touching the registry schema, the CLI, the config format, or
an adapter contract, open an issue first: the design invariants above are not
negotiable, and finding that out after writing the code wastes your evening.

This is maintained by one person. Expect a first response within a week, and say
so on the pull request if two weeks pass, because it means it was missed.
Security issues go to the private channel in [`SECURITY.md`](SECURITY.md), never
a public issue.
