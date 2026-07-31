# Security Policy

## Reporting a vulnerability

Please report security issues privately by email to **alberto.rsesc@protonmail.com**
rather than opening a public issue. Include a description, reproduction steps,
and the impact you observed. You can expect an initial response within a few
days, and coordinated disclosure once a fix is available.

## Design posture

planeops is built to keep its own attack surface small:

- **No daemon, no open ports.** Every verb is a short-lived command that exits.
  The optional `plane-mcp` server is the one long-lived process, and only when
  the user starts it: it speaks stdio (no listening port) and never mutates the
  managed machine; its one non-pure tool refreshes the recorded snapshot, and
  there is no mutation tool.
- **No mutation without a rendered plan and an explicit confirmation.**
  `observe`, `drift`, `status`, and `mcp` never mutate the machine. `apply`
  confirms per change (answering `a` extends the yes to the rest of that
  domain); `plane schedule` and `plane import --write` preview what they will
  write (the paths and the proposed content or entry) and confirm before
  writing (`--yes` opts a script in explicitly). The scheduled job runs
  `reconcile` (observe + drift) only.
- **Secrets are references in every stored artifact.** The registry, snapshots,
  reports, diffs, and the apply journal record references and presence
  metadata only. A value is decrypted in exactly one place, inside the secrets
  adapter's confirmed materialization step, and lands only in the declared
  target file (created 0600 under 0700 parents, replaced atomically, symlinked
  targets refused, containment-checked against allowed bases). The engine
  enforces this in code: requesting a value anywhere else raises.
- **Adapters shell out to local tools** (for example `launchctl`) through a
  single injected command seam with per-operation timeouts, and make no network
  calls of their own.

## Scope

`observed/` snapshots describe a specific machine (services, paths, hostname)
and are gitignored by default. Machine-specific material (real registry entries,
snapshots, and any inventory of a real host) belongs in a separate private
instance, never in this public repository.
