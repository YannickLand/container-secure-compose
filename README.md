# container-secure-compose

[![CI](https://github.com/YannickLand/container-secure-compose/actions/workflows/ci.yml/badge.svg)](https://github.com/YannickLand/container-secure-compose/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/YannickLand/container-secure-compose/branch/main/graph/badge.svg)](https://codecov.io/gh/YannickLand/container-secure-compose)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A privilege-minimised Docker Compose configuration generator. Produces
security-aware `docker-compose.yml` files from an abstract application
description, using composable *building blocks* designed for minimal
container privileges.

Developers describe their application in a concise YAML config — naming
services and picking building blocks — without needing to know the details
of Docker Compose security options. The tool enforces secure defaults and
supports principled escalations when elevated access is genuinely required.

## Concepts

### Building blocks

A building block is a named snippet of Docker Compose service (or network,
or volume) configuration that encodes a security-relevant design decision.
Each block carries `_meta` with a description, a security impact level
(`low`, `medium`, `high`, `critical`), and an `escalation` flag.

The **`standard`** block is the default for application containers. It
applies:
- `cap_drop: ALL` — drops every Linux capability
- `security_opt: no-new-privileges:true` — prevents privilege escalation via
  setuid binaries
- `user: nobody` — runs as an unprivileged user

Escalations are explicit opt-ins (`host-network`, `add-cap-net-admin`, …).
Insecure choices are therefore named and visible in the input config.

### Properties

Any Docker Compose key/value pair that is not covered by a building block
can be added in the `properties` section. Properties override building block
values on collision.

### Application templates

Pre-composed input configs for common architectures (see `templates/`). Use
them as starting points for new applications.

## Installation

```bash
pip install -e .
```

Requires Python 3.11+.

## Quick start

```bash
csc generate examples/ping-tracker/app_config.yaml
```

Output is written to `output/ping-tracker/docker-compose.yml` and a security
report is printed:

```
Generated: output/ping-tracker/docker-compose.yml

Security report
---------------
  Service         cap_drop   no-new-priv  non-root   read-only  impact    notes
  --------------------------------------------------------------------------------------------------------
  tracker         yes        yes          yes        no         low
  ui              yes        yes          yes        no         low
  init            yes        no           no         no         HIGH      cap_add: CHOWN, DAC_OVERRIDE
```

## Input config format

```yaml
app_name: my-application      # required — also used as output folder name
version: "3"                  # optional Docker Compose file version

services:
  - name: <service-name>
    building_blocks:
      - <block-name>          # zero or more blocks from building_blocks/services/
    properties:               # any Docker Compose service keys
      image: my-image:latest
      restart: unless-stopped

networks:
  - name: <network-name>
    building_blocks:
      - <block-name>          # from building_blocks/networks/
    properties: {}

volumes:
  - name: <volume-name>
    building_blocks:
      - <block-name>          # from building_blocks/volumes/
    properties: {}
```

## Available building blocks

### services/

| Block | Impact | Description |
|---|---|---|
| `standard` | low | Secure baseline: cap_drop ALL, no-new-privileges, non-root |
| `drop-capabilities` | low | cap_drop: ALL |
| `no-new-privileges` | low | security_opt: no-new-privileges:true |
| `non-root` | low | user: nobody |
| `drop-privileges` | low | Combination of the above three |
| `init` | medium | Init container pattern (CHOWN + DAC_OVERRIDE, restart: no) |
| `wait-init` | low | depends_on: init |
| `sidecar` | low | restart: always |
| `add-cap-net-admin` | medium | cap_add: NET_ADMIN |
| `add-cap-net-raw` | medium | cap_add: NET_RAW |
| `host-network` | **high** | network_mode: host + NET_ADMIN + NET_RAW |
| `layer2-network` | **high** | MACVLAN network attachment + NET_ADMIN + NET_RAW |
| `mirroring-setup` | **high** | One-shot host traffic mirroring setup |
| `read-only` | low | Mount root filesystem read-only (`read_only: true`) |
| `root` | **high** | user: root |
| `privileged` | **critical** | privileged: true |

### networks/

| Block | Impact | Description |
|---|---|---|
| `app-internal` | low | Isolated internal bridge |
| `layer2` | high | MACVLAN network |

### volumes/

| Block | Impact | Description |
|---|---|---|
| `data` | low | Named Docker volume (empty declaration) |

Run `csc list-blocks` to see the same list with full descriptions at runtime.

## CLI reference

```
csc generate <config>
    Generate docker-compose.yml from a CSC application config.

    Options:
      -o, --output PATH           Output file path (default: output/<app_name>/docker-compose.yml)
      -b, --blocks-dir PATH       Building blocks directory (default: building_blocks/ near config or CWD)
      --stdout                    Print YAML to stdout instead of writing a file
      --no-report                 Suppress the security report
      --report-format [text|json] Security report format (default: text)

csc validate <config>
    Validate the config and check that all referenced building blocks exist.
    No files are written.

csc list-blocks
    List all available building blocks with descriptions and impact levels.

    Options:
      -b, --blocks-dir PATH
      -c, --category [services|networks|volumes]

csc explain <config>
    Show what each building block contributes per service. No files written.

csc audit <compose-file>
    Run a security report against any existing docker-compose.yml
    (does not require a csc config file).

    Options:
      --report-format [text|json]

csc diff <config> <compose-file>
    Compare what csc would generate against an existing docker-compose.yml.
    Highlights security regressions and exits non-zero when any are found.

    Options:
      -b, --blocks-dir PATH
```

## Security report

After generation the tool prints a table with one row per service:

- **cap_drop** — `cap_drop: ALL` present
- **no-new-priv** — `no-new-privileges` security option present
- **non-root** — `user` is not root/0
- **read-only** — `read_only: true` set
- **impact** — derived worst-case label: `low / medium / HIGH / CRITICAL`
- **notes** — any active escalations (host-network, cap_add, privileged)

## Custom building blocks

Create a `building_blocks/` directory next to your application config (or
pass `--blocks-dir`). Any `.yaml` file placed in `services/`, `networks/`,
or `volumes/` becomes available as a building block. Use the `_meta` key to
document it:

```yaml
_meta:
  name: my-block
  description: "What this block does and why."
  security_impact: low    # low | medium | high | critical
  escalation: false
  incompatible_with: []   # names of blocks that conflict with this one

# Everything below _meta is merged into the service/network/volume config:
environment:
  LOG_LEVEL: info
```

The `_meta` key is stripped before writing the compose output.

## Architecture templates

Ready-to-use starting points are in `templates/`:

| Template | Description |
|---|---|
| `init-workload-ui.yaml` | Init container + workload + web UI |
| `sidecar-workload.yaml` | Workload + privilege-minimised sidecar |
| `init-workload-mirroring.yaml` | Workload + read-only traffic monitor |

Copy a template, fill in the placeholder values, and run `csc generate`.

## Related projects

- **[container-net-mirroring](https://github.com/YannickLand/container-net-mirroring)** —
  companion tool for the `mirroring-setup` building block. Configures Linux
  `tc` rules that mirror host network traffic into a container without granting
  it host-network access.

## Documentation

| Type | Contents |
|---|---|
| [Tutorial](docs/tutorials/getting-started.md) | Getting started: your first secure Compose file |
| [How-to guides](docs/how-to-guides/) | Audit an existing Compose file, add custom blocks |
| [Explanation](docs/explanation/security-model.md) | Security model and building-block design |
| [Reference](docs/reference/cli-reference.md) | Full CLI reference and building-blocks reference |

## Architecture

```
csc/                    Core package
  cli.py                Click CLI entry point — all commands
  generator.py          Config loading, block merging, Compose output
  reporter.py           Security report analysis and formatting
  models.py             Pydantic models for app config and block metadata
building_blocks/        Built-in building blocks (YAML snippets)
  services/             Service-level blocks (standard, host-network, …)
  networks/             Network blocks (app-internal, layer2)
  volumes/              Volume blocks (data)
templates/              Ready-to-use app_config.yaml starting points
examples/               Worked examples with input config and generated output
tests/                  pytest test suite
docs/                   Diataxis documentation
```

## Development

```bash
# Install with dev extras
pip install -e ".[dev]"

# Run tests (unit only, fast)
pytest -m "not integration"

# Run tests with full coverage report
pytest --cov=csc --cov-report=term-missing

# Lint
ruff check .

# Type check
mypy csc/

# Security scan — source
bandit -r csc/ -ll

# Security scan — dependencies
pip-audit
```

## License

[MIT](LICENSE)
