# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project aims
to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Engine core: entry schema, the `observe`/`plan`/`execute` adapter contract,
  package-scan adapter discovery, and an injectable platform seam.
- `plane` CLI with four verbs: `observe`, `drift`, `apply`, and
  `import stackfile`.
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
  (`mcp-sources.yaml`) and merges them by name across tools, so a server wired
  into one tool but not another is visible as a reuse candidate. Observe-only,
  and names no specific tool: the sources are configuration, not code.
- `Ctx` now carries the instance `repo_root`, so an adapter can read
  instance-level configuration.
- `chezmoi` adapter: delegates config/dotfile reproduction to chezmoi. Observes
  managed files and their drift (`chezmoi status`) and converges a drifted file by
  invoking `chezmoi apply`; chezmoi owns the writing, secrets, and templating while
  tarmac governs it as one domain.
- Drift triage surfaces a general content-drift signal (`facts.drifted`) from any
  adapter, routed by the entry's tolerance.
- `plane apply` records every run to an immutable `applied.jsonl`, re-observes so
  drift reflects it, honors `owner: human` (never writes it), converges in `phase`
  order, and contains a crashing adapter instead of aborting the run.
- `DRIFT.md` report with Alerts / Report / Auto-folded / Uncovered / Re-auth
  sections, and a non-zero exit code when alerts exist.

[Unreleased]: https://github.com/albertorsesc/tarmac/commits/main
