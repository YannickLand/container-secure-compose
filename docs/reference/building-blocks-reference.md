# Building Blocks Reference

Complete reference for all built-in building blocks.
For guidance on creating custom blocks see
[How to add a custom building block](../how-to-guides/how-to-add-custom-block.md).

---

## services/

### `standard`

| Field | Value |
|---|---|
| Impact | `low` |
| Escalation | No |

The recommended default for all application containers.

```yaml
cap_drop:
  - ALL
security_opt:
  - no-new-privileges:true
user: nobody
```

---

### `drop-capabilities`

| Field | Value |
|---|---|
| Impact | `low` |
| Escalation | No |

```yaml
cap_drop:
  - ALL
```

---

### `no-new-privileges`

| Field | Value |
|---|---|
| Impact | `low` |
| Escalation | No |

```yaml
security_opt:
  - no-new-privileges:true
```

---

### `non-root`

| Field | Value |
|---|---|
| Impact | `low` |
| Escalation | No |

```yaml
user: nobody
```

---

### `drop-privileges`

| Field | Value |
|---|---|
| Impact | `low` |
| Escalation | No |

Combination of `drop-capabilities`, `no-new-privileges`, and `non-root`.

---

### `read-only`

| Field | Value |
|---|---|
| Impact | `low` |
| Escalation | No |

Mounts the container root filesystem read-only.

```yaml
read_only: true
```

Applications that write to disk need explicit `tmpfs` or volume mounts for
writable paths.

---

### `init`

| Field | Value |
|---|---|
| Impact | `medium` |
| Escalation | Yes |

Init container pattern: runs once to set up shared volumes, then exits.

```yaml
restart: "no"
cap_drop:
  - ALL
cap_add:
  - CHOWN
  - DAC_OVERRIDE
```

Escalation rationale: CHOWN and DAC_OVERRIDE are required to set ownership on
shared volumes before the application starts.

---

### `wait-init`

| Field | Value |
|---|---|
| Impact | `low` |
| Escalation | No |

Adds a dependency on the `init` service so this service starts only after init exits:

```yaml
depends_on:
  - init
```

---

### `sidecar`

| Field | Value |
|---|---|
| Impact | `low` |
| Escalation | No |

```yaml
restart: always
```

---

### `add-cap-net-admin`

| Field | Value |
|---|---|
| Impact | `medium` |
| Escalation | Yes |

```yaml
cap_add:
  - NET_ADMIN
```

---

### `add-cap-net-raw`

| Field | Value |
|---|---|
| Impact | `medium` |
| Escalation | Yes |

```yaml
cap_add:
  - NET_RAW
```

---

### `host-network`

| Field | Value |
|---|---|
| Impact | `high` |
| Escalation | Yes |

Shares the host network namespace with the container:

```yaml
network_mode: host
cap_add:
  - NET_ADMIN
  - NET_RAW
```

Use only when the container must bind to host ports or capture raw traffic
at the host level. Incompatible with Docker-managed networks on the same service.

---

### `layer2-network`

| Field | Value |
|---|---|
| Impact | `high` |
| Escalation | Yes |

Attaches the service to a MACVLAN network with L2 access:

```yaml
cap_add:
  - NET_ADMIN
  - NET_RAW
```

Used together with the `layer2` network building block.

---

### `mirroring-setup`

| Field | Value |
|---|---|
| Impact | `high` |
| Escalation | Yes |

One-shot host traffic mirroring setup container. Requires host-network access.

---

### `root`

| Field | Value |
|---|---|
| Impact | `high` |
| Escalation | Yes |

```yaml
user: root
```

Avoid unless absolutely required. Document the reason in the config.

---

### `privileged`

| Field | Value |
|---|---|
| Impact | `critical` |
| Escalation | Yes |

```yaml
privileged: true
```

Grants the container root-equivalent access to the host. Only use for
special system containers (e.g. a hardware initialisation container).

---

## networks/

### `app-internal`

| Field | Value |
|---|---|
| Impact | `low` |
| Escalation | No |

An isolated internal bridge network. Services on this network cannot be
reached from outside Docker.

```yaml
driver: bridge
internal: true
```

---

### `layer2`

| Field | Value |
|---|---|
| Impact | `high` |
| Escalation | Yes |

A MACVLAN network that gives the container direct L2 access to the host
network segment. Required for traffic monitoring use cases.

```yaml
driver: macvlan
```

---

## volumes/

### `data`

| Field | Value |
|---|---|
| Impact | `low` |
| Escalation | No |

An empty named Docker volume declaration:

```yaml
{}
```

---

## `_meta` schema

Every building block may include a `_meta` section. All fields are optional.

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | string | filename stem | Display name |
| `description` | string | `""` | Human-readable purpose |
| `security_impact` | `low\|medium\|high\|critical` | `low` | Worst-case impact when this block is used |
| `escalation` | bool | `false` | Whether the block grants elevated privileges |
| `incompatible_with` | list of strings | `[]` | Block names that must not be combined with this one |

The `_meta` key is stripped before writing the Compose output.
