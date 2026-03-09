# Getting Started: your first secure Compose file

This tutorial walks you through installing **container-secure-compose** and
generating your first security-hardened `docker-compose.yml` from scratch.
By the end you will have a working Compose file for a two-service application
and understand what the security report tells you.

## What you will need

- Python 3.11 or later
- Git (to clone the repository)
- Docker Compose v2

---

## Step 1 — Install container-secure-compose

Clone the repository and install the package in a virtual environment:

```bash
git clone https://github.com/YannickLand/container-secure-compose.git
cd container-secure-compose
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .
```

Verify the installation:

```bash
csc --version
```

---

## Step 2 — Create your application config

Create a file called `my-app/app_config.yaml` with the following content:

```yaml
app_name: my-app

services:
  - name: api
    building_blocks:
      - standard       # cap_drop ALL, no-new-privileges, non-root user
    properties:
      image: my-api:1.0.0
      ports:
        - "8080:8080"
      restart: unless-stopped

  - name: db
    building_blocks:
      - standard
    properties:
      image: postgres:16-alpine
      restart: unless-stopped
      environment:
        POSTGRES_PASSWORD_FILE: /run/secrets/db_password
```

The `standard` building block applies three security controls to every service:
`cap_drop: ALL`, `security_opt: no-new-privileges:true`, and `user: nobody`.
For more detail on why these matter, see the
[Security model explanation](../explanation/security-model.md).

---

## Step 3 — Generate the Compose file

Run the generator, pointing it at the config you just created. The
`building_blocks/` directory bundled with the tool will be found automatically:

```bash
csc generate my-app/app_config.yaml
```

The tool writes the output to `output/my-app/docker-compose.yml` and prints
a security report:

```
Generated: output/my-app/docker-compose.yml

Security report
---------------
  Service          cap_drop   no-new-priv  non-root   read-only  impact    notes
  ---------------------------------------------------------------------------------
  api              yes        yes          yes        no         low
  db               yes        yes          yes        no         low
```

Both services show `low` impact — they are using secure defaults.

---

## Step 4 — Inspect the generated file

Open `output/my-app/docker-compose.yml`:

```yaml
services:
  api:
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    user: nobody
    image: my-api:1.0.0
    ports:
      - 8080:8080
    restart: unless-stopped
  db:
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    user: nobody
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
```

The security options were injected by the `standard` block — you did not need
to write them manually.

---

## Step 5 — Validate the config

Before committing, check that the config is well-formed:

```bash
csc validate my-app/app_config.yaml
```

```
Config is valid. (my-app/app_config.yaml)
```

---

## What you achieved

- Installed container-secure-compose
- Wrote a concise application config using building blocks
- Generated a security-hardened `docker-compose.yml`
- Read and understood the security report

## Next steps

- Add `read-only` to your services: [How to add a custom building block](../how-to-guides/how-to-add-custom-block.md)
- Audit an existing Compose file: [How to audit an existing docker-compose.yml](../how-to-guides/how-to-audit-existing-compose.md)
- Understand why these controls matter: [Security model](../explanation/security-model.md)
- See every command and option: [CLI reference](../reference/cli-reference.md)
