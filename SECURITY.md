# Security Policy

## Reporting a vulnerability

Please report security issues privately by email to **alberto.rsesc@protonmail.com**
rather than opening a public issue. Include a description, reproduction steps,
and the impact you observed. You can expect an initial response within a few
days, and coordinated disclosure once a fix is available.

## Design posture

planeops is built to keep its own attack surface small:

- **No daemon, no open ports.** Every verb is a short-lived command that exits.
  There is no long-running process to compromise.
- **Read by default.** `observe` and `drift` never mutate the machine. Only
  `apply` writes, and only after rendering a diff and receiving an explicit
  confirmation per change.
- **Secrets are references, never values.** Secret values never enter the
  engine's core, the repository, generated snapshots, or reports. The registry
  records only references and metadata.
- **Adapters shell out to local tools** (for example `launchctl`) through a
  single injected command seam, with no network calls of their own.

## Scope

`observed/` snapshots describe a specific machine (services, paths, hostname)
and are gitignored by default. Machine-specific material (real registry entries,
snapshots, and any inventory of a real host) belongs in a separate private
instance, never in this public repository.
