# CLI Reference

Complete reference for every `csc` command. For a guided introduction see the
[Getting started tutorial](../tutorials/getting-started.md).

---

## Global options

```
csc [OPTIONS] COMMAND [ARGS]...
```

| Option | Description |
|---|---|
| `--version` | Show the installed version and exit |
| `--help` | Show help and exit |

---

## `csc generate`

Generate a `docker-compose.yml` from a CSC application config.

```
csc generate [OPTIONS] CONFIG
```

**Arguments**

| Argument | Description |
|---|---|
| `CONFIG` | Path to the CSC application config YAML file (required) |

**Options**

| Option | Default | Description |
|---|---|---|
| `-o, --output PATH` | `output/<app_name>/docker-compose.yml` | Output file path |
| `-b, --blocks-dir PATH` | `building_blocks/` next to config or CWD | Building blocks directory |
| `--stdout` | off | Print YAML to stdout instead of writing a file |
| `--no-report` | off | Suppress the security report |
| `--report-format [text\|json]` | `text` | Security report format |

**Exit codes**

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Config validation error or blocks not found |

**Example**

```bash
csc generate app_config.yaml --report-format json --stdout
```

---

## `csc validate`

Validate a CSC config file and check that all referenced building blocks exist.
No files are written.

```
csc validate [OPTIONS] CONFIG
```

**Arguments**

| Argument | Description |
|---|---|
| `CONFIG` | Path to the CSC application config YAML file |

**Options**

| Option | Description |
|---|---|
| `-b, --blocks-dir PATH` | Building blocks directory |

**Exit codes**

| Code | Meaning |
|---|---|
| 0 | Config is valid |
| 1 | Validation error or missing blocks |

---

## `csc list-blocks`

List all available building blocks with descriptions and impact levels.

```
csc list-blocks [OPTIONS]
```

**Options**

| Option | Description |
|---|---|
| `-b, --blocks-dir PATH` | Building blocks directory |
| `-c, --category [services\|networks\|volumes]` | Filter by category |

**Output format**

```
services/
  standard                       [low]
    Secure baseline: cap_drop ALL, no-new-privileges, non-root
  host-network                   [high] [escalation]
    network_mode: host + NET_ADMIN + NET_RAW
```

---

## `csc explain`

Show what each building block contributes to each service. No files written.
Useful for understanding what a config will produce before generating.

```
csc explain [OPTIONS] CONFIG
```

**Arguments**

| Argument | Description |
|---|---|
| `CONFIG` | Path to the CSC application config YAML file |

**Options**

| Option | Description |
|---|---|
| `-b, --blocks-dir PATH` | Building blocks directory |

---

## `csc audit`

Run a security report against any existing `docker-compose.yml`.
Does not require a CSC config file.

```
csc audit [OPTIONS] COMPOSE_FILE
```

**Arguments**

| Argument | Description |
|---|---|
| `COMPOSE_FILE` | Path to any Docker Compose YAML file |

**Options**

| Option | Default | Description |
|---|---|---|
| `--report-format [text\|json]` | `text` | Security report format |

**Exit codes**

| Code | Meaning |
|---|---|
| 0 | Success (report printed regardless of security findings) |
| 1 | YAML parse error |

---

## `csc diff`

Compare what `csc generate` would produce against an existing `docker-compose.yml`.
Highlights security regressions (missing controls in the existing file) and
improvements (controls present in the existing file but absent in the generated
output). Exits non-zero when regressions are found.

```
csc diff [OPTIONS] CONFIG COMPOSE_FILE
```

**Arguments**

| Argument | Description |
|---|---|
| `CONFIG` | Path to the CSC application config YAML file |
| `COMPOSE_FILE` | Path to the existing `docker-compose.yml` to compare against |

**Options**

| Option | Description |
|---|---|
| `-b, --blocks-dir PATH` | Building blocks directory |

**Exit codes**

| Code | Meaning |
|---|---|
| 0 | No regressions |
| 1 | One or more security regressions detected |

---

## Security report format

The security report (from `generate`, `audit`, and `diff`) has one row per service:

| Column | Description |
|---|---|
| `Service` | Service name |
| `cap_drop` | `yes` if `cap_drop: ALL` is present |
| `no-new-priv` | `yes` if `security_opt: no-new-privileges:true` is present |
| `non-root` | `yes` if `user` is set to a non-root identity |
| `read-only` | `yes` if `read_only: true` is set |
| `impact` | Worst-case label: `low`, `medium`, `HIGH`, `CRITICAL` |
| `notes` | Active escalations (e.g. `host-network`, `cap_add: NET_ADMIN`, `privileged mode`) |

When `--report-format json` is used, each row is a JSON object with the same
fields plus `cap_drop_all` (bool), `no_new_privileges` (bool), `non_root`
(bool), `read_only_fs` (bool), `host_network` (bool), `privileged` (bool),
`cap_add` (list of strings).
