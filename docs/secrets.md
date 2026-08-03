# Secrets, without values

<p align="center">
  <img src="https://raw.githubusercontent.com/albertorsesc/planeops/main/docs/assets/secrets-vault.png" alt="A vault: keys visible, values sealed" width="360">
</p>

The shipped store is [sops](https://github.com/getsops/sops) +
[age](https://github.com/FiloSottile/age): key names stay readable, values stay
encrypted. `plane observe` can answer "is the OpenRouter key configured?"
without decrypting anything, and snapshots, reports, and diffs never carry a
value.

The whole flow is four steps, in order:

1. **Declare** the secret as a registry entry (what exists and where it goes).
2. **`plane secrets init`**, once per machine: identity, rules, empty store.
3. **`plane secrets add <name>`**, once per secret: the value goes in encrypted.
4. **`plane apply`** materializes it into the file the entry declares.

Until step 3, `plane drift` flags the declared secret as "not configured";
after it, presence is green and only step 4 ever decrypts.

## 1. Declare: a governed secret is one registry entry

```yaml
- id: secrets/openrouter-api-key
  adapter: secrets
  domain: secret
  lifecycle: active
  intent: LLM gateway key for local tooling
  secrets:
    - ref: secret://openrouter-api-key
      injected_as: file:~/.config/llm/env#OPENROUTER_API_KEY
```

Which store serves a ref is instance configuration, so swapping stores touches
zero entries.

## 2. Bootstrap the store, once per machine

Runnable from anywhere; nothing depends on the working directory:

```console
$ plane secrets init
secrets init will write:
  /Users/you/Library/Application Support/sops/age/keys.txt (new age identity via age-keygen)
  /Users/you/planeops/.sops.yaml (sops creation rule for this store)
  /Users/you/planeops/secrets.sops.yaml (empty encrypted store)
proceed? (y/N) y
```

It reuses an existing age identity when one exists (or pass `--age-key <path>`),
and creates a new one where sops itself looks on your OS, so decryption needs no
environment setup. Re-initializing over an existing store is refused, and a
store that turns out to hold plaintext is a loud failed-scan alert, never a
quiet "configured".

## 3. Put each value in

```console
$ plane secrets add openrouter-api-key
add 'openrouter-api-key' in /Users/you/planeops/secrets.sops.yaml
value for 'openrouter-api-key' (input hidden):
repeat to confirm:
added 'openrouter-api-key' in /Users/you/planeops/secrets.sops.yaml
```

The value is typed blind (twice, to catch typos) and never appears on a
command line, in the environment, or in any output. Piping works for password
managers: `op read op://vault/key | plane secrets add openrouter-api-key --yes`.
Rotating an existing value requires `--force`.

## 4. When a value moves

A value is decrypted exactly once, inside a confirmed `apply`, into the one file
the entry declares. The write is `0600`, refuses symlinks, and is
containment-checked against the allowed base directories. Everything outside
that moment sees names and presence only: the redaction gate hands adapters a
handle with no method that can yield a value.
