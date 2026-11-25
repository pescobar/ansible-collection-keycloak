# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

`pescobar.keycloak` — an Ansible **collection** (not a single role) to deploy and
configure Keycloak. Two roles:

- `roles/keycloak_deploy` — stands up Keycloak + Caddy (TLS) + PostgreSQL as a
  Docker Compose stack on a target host.
- `roles/keycloak_cfg` — configures a *running* Keycloak (realms, groups,
  clients, identity providers + mappers, realm keys, required actions,
  authentication flows, user profiles) via the admin REST API.

Roles are referenced by FQCN: `pescobar.keycloak.keycloak_deploy`,
`pescobar.keycloak.keycloak_cfg`.

## Repository layout

```
galaxy.yml                 # collection metadata + dependencies
meta/runtime.yml           # requires_ansible
requirements.yml           # controller-side collection deps (galaxy.yml deps + middleware_automation.keycloak)
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
  matching `middleware_automation.keycloak.keycloak_*` module via `args:`.
  Therefore list items use the **module's native parameter names** — do not
  invent role-specific
  aliases. This is why realm keys use `parent_id` (they are Keycloak *components*)
  while realms/groups/clients/idps use `realm`. A past decision explicitly kept
  `parent_id` rather than normalizing to `realm`, to stay 1:1 with the module docs.
- **User profiles are the one exception to the pass-through.** They are applied by
  `ansible.builtin.uri` PUTting `keycloak_cfg_user_profiles[].profile` straight to
  `/admin/realms/{realm}/users/profile`, not via `keycloak_userprofile`. On
  Keycloak 24+ that endpoint is the live profile store; the module still writes the
  legacy `/components` API, which KC 26 ignores (it creates duplicate components and
  never updates the effective profile — verified: three orphan components, profile
  unchanged). So the item shape is `{realm, profile}` where `profile` is the raw
  Keycloak profile JSON (camelCase keys, kebab-case validator ids), applied
  idempotently (GET, compare, PUT only on diff). Do not "fix" this back to the
  module.
- **`_keycloak_cfg_auth` carries `auth_realm` (login realm, e.g. master) but no
  `realm` key**, so one admin login manages many realms; each item names its own
  target realm.
- **Secrets belong in Vault.** `keycloak_deploy` refuses to run while admin/db
  passwords hold their placeholder defaults. `keycloak_cfg` tasks run with
  `no_log: "{{ keycloak_cfg_no_log }}"` (default true).

## Deploy role gotchas

- **Does not install Docker.** `tasks/preflight.yml` only *verifies* Docker Engine
  + Compose v2 (`docker version`, `docker compose version`) and fails with a
  clear message otherwise.
- **Public URLs assume port 443.** `KC_HOSTNAME=https://<hostname>` carries no
  port, so `keycloak_deploy_https_port` other than 443 only works behind
  something that still serves 443. The Caddyfile relies on `reverse_proxy`'s
  default header forwarding; don't re-add `header_up ... {host}` (`{host}` drops
  the port).
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
- `middleware_automation.keycloak >= 3.1.3` (cfg) — supplies every `keycloak_*`
  module the role calls. The Keycloak modules left `community.general` in 14.0
  (only deprecated redirects remain, removed in 16), and the old
  `community.general` versions are buggy on Keycloak 25+ (flow priority reset,
  no generated realm keys), so the role does not use `community.general` at all.
  It needs ansible-core >= 2.16 (hence `requires_ansible`).
  **Deliberately not in `galaxy.yml` `dependencies`** (the user's choice: it is
  documented and listed in `requirements.yml`, and Ansible's own "couldn't
  resolve module/action" error is the check — no sanity task). Apart from that
  exception, keep `galaxy.yml` and `requirements.yml` in sync.
- `ansible.utils >= 2.0.0` (cfg) — only for `fact_diff`, which renders the user
  profile `--diff` (the `uri` PUT that applies it cannot emit one). Bundled with
  the ansible community package.

## Validating changes in this environment

There is no system Ansible here. Quick checks are done with Python:

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
  `auth_realm`) and inline sub-structures (IdP `mappers`, user-profile `profile`).
- **Integration:** `uv venv` + `uv pip install 'ansible==10.3.0'` (or latest) plus
  `ansible-galaxy collection install middleware_automation.keycloak`, then run
  `keycloak_deploy` locally with ports bound to `127.0.0.1` and point
  `keycloak_cfg` at it (`keycloak_cfg_validate_certs: false`). Caddy serves
  `localhost` with its internal CA. Run the role twice: the second run should
  only report the known always-changed tasks (README "Idempotency").

There is no molecule/CI harness in the repo yet.

## Seeding keycloak_cfg vars from an existing realm

Two reverse tools, both emitting flat `keycloak_cfg_*` YAML that is a
**scaffold to review**, never a guaranteed drop-in. By default neither writes
secrets in cleartext (only the converter's opt-in `--with-secrets` does).

- **Preferred — `roles/keycloak_cfg/files/gen_vars_from_export.py`** (offline).
  Consumes a native `kc.sh export` JSON and does a *curated* camelCase→snake_case
  map to module-native option names, turning every secret into a named
  `vault_*` placeholder (client secrets, OIDC broker secrets, and realm-key
  private keys — the last only exist in a native export, not over REST). The role
  never calls it. `--with-secrets` inlines real secret values instead (warns on
  stderr; header flags them via `SECRETS_INLINED`). Because `keycloak_cfg` is pure
  pass-through, the converter must **only emit module-native keys** — do not
  inject annotation keys into items (notes/omissions go in the header comment via
  the `NOTES` list, secrets via `VAULT_VARS` / `SECRETS_INLINED`). One realm in →
  one file out; multi-realm export lists are merged.
- **Fallback — `playbooks/export_realm.yml`** (REST, no host access). Raw
  representation dump needing manual prune/reshape (read-only fields the modules
  reject, empty values, list-valued component configs). Client secrets are
  dropped (Keycloak 26 returns them in cleartext); IdP secrets and realm-key
  private keys come back masked. The user chose to keep it a raw dump rather
  than route it through the converter.

## Commit conventions

End commit messages with:
`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
