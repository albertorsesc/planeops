# Footprint: tools discovered by the traces they leave

Package managers know what they installed. Nothing knows about the tool a
curl-pipe script dropped into `~/.config` two years ago, the archived agent
still holding a directory in home, or the app whose only remaining evidence
is an Application Support folder. The footprint adapter finds all of it by
scanning the places tools conventionally leave config, one level deep, and
turning every trace into an observation the drift loop can govern.

## Configure the conventions

Roots are configuration in `instance.yaml`; the engine hardcodes no
convention and no tool name. The usual block:

```yaml
footprint:
  roots:
    - {label: xdg-config, path: ~/.config}
    - {label: xdg-data, path: ~/.local/share}
    - {label: xdg-state, path: ~/.local/state}
    - {label: home-dot, path: "~", dot_only: true}
    - {label: app-support, path: ~/Library/Application Support, os: darwin}
```

- `path` must be `~`-anchored or absolute; home itself is quoted `"~"`
  because YAML reads a bare `~` as null (the error says so if you forget).
- `dot_only: true` scans only dot-children, which is what makes `"~"` mean
  "home dotfiles" rather than everything in home.
- `os: darwin|linux` confines a root to that system, validated against the
  discovered platforms, so one block travels to every machine and a typo
  fails the scan loudly.
- No `footprint:` section, no scan: discovery is opt-in per instance.

## One tool, many traces

The same tool across roots merges into a single observation: `~/.ollama`,
`~/.config/ollama`, and an app-support `Ollama` are one tool with three
footprints (path, kind, convention, and a symlink flag when linked). A
configured root is never itself a tool, on any OS and through symlinks, so
`.config` and `.local` don't show up as discoveries.

Debris never becomes a question: OS artifacts (`.DS_Store`, `.Trash`),
shell and editor state (`*_history`, `.viminfo`, session dirs), backup
copies (`*.bak`, `*~`, `._*`), and the cache dir are skipped by on-disk
name before anything merges. `ignore:` adds instance-specific patterns;
`ignore_defaults: false` drops the built-in list; registry `unmanaged`
globs remain the id-level knob above both.

## Governance without double-asking

A discovered tool whose name matches another adapter's declared entry
(`~/.config/gh` when `pkg-brew/gh` is in the registry, `~/.zshrc` when
chezmoi manages `.zshrc`) is attributed to that entry via the `governed_by`
fact instead of asking for its own. Drift skips attributed traces while the
owning entry exists and resurfaces them the moment it is deleted, and
`plane import observed` proposes only the tools with no decision on record.
An always-on observation alerts regardless of attribution.

Everything else follows the normal lifecycle: declare a discovery `active`
and it is governed; `parked` sleeps silently; retire it and drift alerts
until the trace is actually gone, then asks you to remove the entry.

## The boundary

Discovery is stat-only. Nothing is ever opened, so a credential-bearing
config contributes its name and shape, never its contents, and a mode-000
directory observes like any other. A root the scan cannot read or traverse
refuses loudly into the failed-scan alert, naming itself and the fix,
because silent partial coverage would read as "covered everything".
