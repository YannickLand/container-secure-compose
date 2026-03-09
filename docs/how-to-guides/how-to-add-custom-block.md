# How to add a custom building block

## When to use this

Use this guide when the built-in building blocks do not cover a specific
security or configuration need for your application — for example, a
project-specific log-volume mount, a custom capability requirement, or an
internal network definition.

---

## Steps

### 1 — Create a `building_blocks/` directory

Place it next to your `app_config.yaml`:

```
my-project/
├── app_config.yaml
└── building_blocks/
    └── services/
        └── my-block.yaml
```

Or pass `--blocks-dir <path>` to point to a shared library of blocks.

### 2 — Write the block YAML

A building block is a partial Docker Compose service (or network, or volume)
config with an optional `_meta` section:

```yaml
_meta:
  name: my-block
  description: "Mounts the application log directory as a read-only volume."
  security_impact: low   # low | medium | high | critical
  escalation: false
  incompatible_with: []  # names of other blocks that conflict with this one

# Everything below _meta is merged into the Compose service config:
volumes:
  - /var/log/myapp:/app/logs:ro
```

The `_meta` key is stripped before writing the Compose output — it is only
used for documentation and conflict detection.

### 3 — Reference the block in your config

```yaml
app_name: my-project

services:
  - name: api
    building_blocks:
      - standard
      - my-block         # <-- reference by filename (without .yaml)
    properties:
      image: my-api:1.0.0
```

### 4 — Verify with `csc explain`

Check that the block is loaded and its contribution is visible:

```bash
csc explain my-project/app_config.yaml
```

```
Application: my-project

services/
  api
    [standard]  Secure baseline: cap_drop ALL, no-new-privileges, non-root  (impact: low)
    [my-block]  Mounts the application log directory as a read-only volume.  (impact: low)
```

### 5 — Generate and inspect

```bash
csc generate my-project/app_config.yaml
```

Confirm the volume mount appears in the generated Compose file.

---

## Impact levels

| Level | When to use |
|---|---|
| `low` | The block only adds harmless config (env vars, volume mounts, labels) |
| `medium` | The block grants limited elevated access (e.g. a single capability) |
| `high` | The block grants significant network or system access |
| `critical` | The block grants root-equivalent access (avoid in almost all cases) |

See the [Security model](../explanation/security-model.md) for the reasoning
behind impact levels.

---

## Declaring incompatibilities

If your block must not be combined with another (e.g. a host-network block
is incompatible with an internal-network block), declare it in `_meta`:

```yaml
_meta:
  name: host-only
  incompatible_with:
    - app-internal
```

CSC will emit a warning when both blocks are applied to the same service.
