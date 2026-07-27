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
- `DRIFT.md` report with Alerts / Report / Auto-folded / Uncovered / Re-auth
  sections, and a non-zero exit code when alerts exist.

[Unreleased]: https://github.com/albertorsesc/control_plane/commits/main
