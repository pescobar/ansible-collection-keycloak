# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

`pescobar.keycloak` — an Ansible **collection** (not a single role) to deploy and
configure Keycloak. Two roles:

- `roles/keycloak_deploy` — stands up Keycloak + Caddy (TLS) + PostgreSQL as a
  Docker Compose stack on a target host.
- `roles/keycloak_cfg` — configures a *running* Keycloak (realms, groups,
  clients, identity providers + mappers, realm keys, user profiles) via the
  admin REST API.

Roles are referenced by FQCN: `pescobar.keycloak.keycloak_deploy`,
`pescobar.keycloak.keycloak_cfg`.

## Repository layout

```
galaxy.yml                 # collection metadata + dependencies
meta/runtime.yml           # requires_ansible
requirements.yml           # controller-side collection deps (mirror of galaxy.yml deps)
CHANGELOG.md               # Keep a Changelog + semver
roles/keycloak_deploy/     # deploy role (defaults, vars, tasks, handlers, templates, meta, README)
roles/keycloak_cfg/        # configure role (defaults, vars, tasks, meta, README)
playbooks/                 # deploy.yml, configure.yml, export_realm.yml
```

## Conventions (important)

- **Variable namespacing is strict.** Every `keycloak_deploy` variable starts with
  `keycloak_deploy_`; every `keycloak_cfg` variable starts with `keycloak_cfg_`.
  Internal-only vars are prefixed with an underscore (`_keycloak_deploy_*`,
  `_keycloak_cfg_*`). Keep this when adding variables.
- **`keycloak_cfg` is a deliberate thin pass-through.** Each item in a
  `keycloak_cfg_*` list is `_keycloak_cfg_auth | combine(item)` and handed to the
  matching `community.general.keycloak_*` module via `args:`. Therefore list items
  use the **module's native parameter names** — do not invent role-specific
  aliases. This is why realm keys and user profiles use `parent_id` (they are
  Keycloak *components*) while realms/groups/clients/idps use `realm`. A past
  decision explicitly kept `parent_id` rather than normalizing to `realm`, to stay
  1:1 with the module docs.
- **`_keycloak_cfg_auth` carries `auth_realm` (login realm, e.g. master) but no
  `realm` key**, so one admin login manages many realms; each item names its own
  target realm.
- **Secrets belong in Vault.** `keycloak_deploy` refuses to run while admin/db
  passwords hold their placeholder defaults. `keycloak_cfg` tasks run with
  `no_log: "{{ keycloak_cfg_no_log }}"` (default true).

## Deploy role gotchas

- **Does not install Docker.** `tasks/preflight.yml` only *verifies* Docker Engine
  + Compose v2 and fails with a clear message otherwise.
- **PostgreSQL 18+ volume mount is `/var/lib/postgresql`, not `.../data`.** The 18
  image stores data in a major-version subdirectory; using `.../data` errors out.
- **Keycloak healthcheck uses bash `/dev/tcp`** against the management port (9000)
  — the official image ships bash but no curl/wget. If pinning a distroless image
  variant, this check must change.
- All three services share the **default Compose network** (no custom networks);
  they resolve each other by service name (`keycloak`, `postgres`).
- Caddy provides automatic HTTPS (Let's Encrypt). `keycloak_deploy_acme_ca` can be
  pointed at LE staging to avoid rate limits while testing.

## Dependencies

- `community.docker >= 3.0.0` (deploy).
- `community.general >= 9.4.0` (cfg) — the floor is 9.4.0 specifically for the
  `keycloak_userprofile` module. Do not lower it without dropping user-profile
  support. Keep `galaxy.yml` and `requirements.yml` in sync.

## Validating changes in this environment

Ansible is **not installed** here, so validation is done with Python:

- **YAML validity:**
  `python3 -c "import yaml; list(yaml.safe_load_all(open('FILE')))"`
- **Template rendering:** the Jinja2 templates (deploy role) can be rendered with a
  throwaway venv. Provide a `comment` filter stub (mimics Ansible's) and feed the
  role defaults as context; assert the rendered `docker-compose.yml` parses as
  YAML:
  ```bash
  python3 -m venv /tmp/jenv && /tmp/jenv/bin/pip install -q jinja2 pyyaml
  ```
- **`keycloak_cfg` merge logic:** simulate `_keycloak_cfg_auth | combine(item)` in
  Python to confirm each item keeps its own `realm`/`parent_id` (distinct from
  `auth_realm`) and inline sub-structures (mappers, `kc_user_profile_config`).

There is no molecule/CI harness in the repo yet.

## Seeding keycloak_cfg vars from an existing realm

Two reverse tools, both emitting flat `keycloak_cfg_*` YAML that is a
**scaffold to review**, never a guaranteed drop-in. Secrets are never emitted in
cleartext.

- **Preferred — `roles/keycloak_cfg/files/gen_vars_from_export.py`** (offline).
  Consumes a native `kc.sh export` JSON and does a *curated* camelCase→snake_case
  map to module-native option names, turning every secret into a named
  `vault_*` placeholder (client secrets, OIDC broker secrets, and realm-key
  private keys — the last only exist in a native export, not over REST). The role
  never calls it. Because `keycloak_cfg` is pure pass-through, the converter must
  **only emit module-native keys** — do not inject annotation keys into items
  (notes/omissions go in the header comment via the `NOTES` list, secrets via
  `VAULT_VARS`). One realm in → one file out; multi-realm export lists are merged.
- **Fallback — `playbooks/export_realm.yml`** (REST, no host access). Raw
  representation dump (camelCase + server-managed fields) needing more manual
  rename/prune; cannot recover realm-key private material.

## Commit conventions

End commit messages with:
`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
