# Security model and building-block design

This document explains the design decisions behind container-secure-compose:
why building blocks exist, how security impact is calculated, and what
trade-offs were made.

No step-by-step instructions appear here — those are in the
[how-to guides](../how-to-guides/how-to-audit-existing-compose.md).

---

## Why building blocks?

Docker Compose is a general-purpose tool. Writing a secure Compose file
requires knowing which Linux capabilities to drop, which security options
to set, and which users to run as — knowledge that is easy to forget or
misconfigure.

Building blocks encode that knowledge once, in a reusable, named unit.
A developer who picks `standard` gets `cap_drop: ALL`,
`security_opt: no-new-privileges:true`, and `user: nobody` without needing
to know what each of those does. A security reviewer can audit the blocks
rather than every individual Compose file.

---

## The standard block

The `standard` block is the secure default for application containers. It
applies three controls:

| Control | Compose key | Effect |
|---|---|---|
| Drop all capabilities | `cap_drop: ALL` | Removes every Linux capability; the process has fewer rights than an unprivileged user |
| No privilege escalation | `security_opt: no-new-privileges:true` | Prevents setuid binaries from elevating privileges |
| Non-root user | `user: nobody` | Process runs as an unprivileged identity |

Together these controls reduce the blast radius of a compromised container.

---

## Explicit escalation model

Security-sensitive configurations are always named, never implicit.

- A container that needs `NET_ADMIN` must include `add-cap-net-admin`.
- A container that runs as root must include `root`.
- A container with host-network access must include `host-network`.

Every escalation block carries a higher `security_impact` level. The
security report aggregates impact across all blocks applied to a service
and surfaces the worst-case label. Escalations are therefore visible both
at code-review time (in `app_config.yaml`) and at runtime (in the report).

---

## Impact levels

| Level | Meaning |
|---|---|
| `low` | All three baseline controls present; no escalations |
| `medium` | One or more baseline controls missing (cap_drop, no-new-priv, or non-root) |
| `high` | Cap additions present, host-network mode, or similar significant escalation |
| `critical` | `privileged: true` — the container has root-equivalent access to the host |

Impact is a worst-case measure: a service with `cap_drop: ALL` AND
`cap_add: NET_ADMIN` reports `high` because `cap_add` is present, even
though most capabilities were dropped.

---

## Properties and override semantics

`properties` in an app config are applied after all building blocks are
merged, with `override=True`. This means:

- A property value always wins over a block value on collision.
- No warning is emitted; the intent to override is explicit.

Block-to-block merges use `override=False`: if two blocks set the same
scalar key to different values, a warning is emitted and the first block's
value is kept. This prevents silent data loss when composing multiple blocks.

List values (e.g. `cap_drop`, `security_opt`, `volumes`) are always union-merged
without duplicates, regardless of the override flag.

---

## What CSC does not do

- **It does not build images.** It only generates the Compose orchestration
  config. Image hardening (non-root user inside the image, minimal base
  image, etc.) is the responsibility of the Dockerfile.
- **It does not enforce runtime policies.** Generated files can be modified
  manually. Use `csc audit` or `csc diff` in CI to detect post-generation regressions.
- **It does not validate image names or tags.** A `latest` tag in `properties`
  is accepted without warning.

---

## Related

- [Getting started tutorial](../tutorials/getting-started.md)
- [CLI reference](../reference/cli-reference.md)
- [Building blocks reference](../reference/building-blocks-reference.md)
