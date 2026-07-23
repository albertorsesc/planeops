# control_plane

Reproduce, observe, and govern a personal AI setup as three planes. `SPEC.md` is the authoritative build spec; `docs/architecture/` is the evidence trail that produced it.

The three planes:

- **Control plane**: decides what runs, where, and under which policy.
- **Data plane**: the executors that do the work (Claude Code, Hermes, agents, MCP servers, local models).
- **Management plane**: the single place where the whole setup is configured, versioned, and observed.

Status: spec complete (`SPEC.md` v0.1), no code yet. Where the docs below conflict with `SPEC.md`, the spec wins.

## Layout

- `docs/architecture/00-machine-inventory.md`: verified inventory of everything AI-related installed on this machine (the current, unplanned "planes").
- `docs/architecture/01-three-planes.md`: the target architecture, mapping the inventory onto the three planes and identifying the gaps.
- `docs/architecture/02-arrangement.md`: repo layout and the observe / diff / decide / apply convergence loop.
- `docs/architecture/03-usage-and-flexibility.md`: measured usage of everything in the inventory, the flexibility requirements that fall out, and the tool-agnostic shape for open-sourcing.
- `docs/architecture/04-architecture-v1.md`: the consolidated architecture (supersedes the target-architecture sections of 01 and 02): engine/instance repo split, kernel + adapters, two-question drift, human-as-reconciler.
- `docs/architecture/05-reproducibility.md`: the primary requirement, corrected: converge the same setup on a new machine. Recipe/data/cache taxonomy, single-writer ownership rule, portable secrets (sops+age), the clean-account rehearsal as the plane's own acceptance test, revised build order.
