# Changelog

All notable changes to the `pescobar.keycloak` collection are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this collection adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- `keycloak_cfg`: apply the declarative user profile through the dedicated
  `/admin/realms/{realm}/users/profile` REST endpoint (`ansible.builtin.uri`,
  idempotent GET/compare/PUT) instead of `community.general.keycloak_userprofile`.
  On Keycloak 24+ that module writes the legacy `/components` API, which KC 26
  ignores — it creates duplicate orphan components and never updates the live
  profile. **Breaking:** `keycloak_cfg_user_profiles` items are now
  `{realm, profile}` where `profile` is the raw Keycloak profile JSON, replacing
  the old `{parent_id, config: {kc_user_profile_config: [...]}, state}` shape.
- `keycloak_cfg`: lower the `community.general` floor back to `>=9.3.0` (the
  version bundled with ansible 10.3.0) now that no user-profile module is used.

### Added

- `keycloak_cfg`: render a before/after `--diff` of pending user-profile changes
  via `ansible.utils.fact_diff` (the `uri` PUT that applies them cannot emit a
  diff). Adds an `ansible.utils >= 2.0.0` dependency (bundled with the ansible
  community package).

### Fixed

- `keycloak_cfg`: give every `loop` its own `loop_var` (`_kc_item`) to silence the
  "loop variable 'item' is already in use" warning when the role is invoked from a
  looping context.
- `gen_vars_from_export.py`: emit multiline PEM certificates/keys as YAML literal
  block scalars (`|`), and emit user profiles as raw `{realm, profile}` JSON that
  the role PUTs verbatim to `/users/profile`.

### Added

- `keycloak_cfg`: `files/gen_vars_from_export.py` — an offline converter that
  turns a native `kc.sh export` realm JSON into flat `keycloak_cfg_*` variables
  with module-native option names and named Vault placeholders for all secrets
  (including realm-key private material, which the REST API never returns). The
  REST-based `playbooks/export_realm.yml` remains as a no-host-access fallback.
  A `--with-secrets` flag inlines real secret values instead of placeholders;
  in that mode the tool warns on stderr and the output header flags the plaintext
  secrets, listing each by the Vault variable name it should be moved to.

## [1.0.0] - 2026-07-23

First release as an Ansible collection. Converts the former standalone role into
`pescobar.keycloak` with two roles.

### Added

- **`keycloak_deploy` role** — deploys Keycloak in production mode behind a Caddy
  TLS-terminating reverse proxy (automatic HTTPS via Let's Encrypt) with a
  PostgreSQL backend, as a Docker Compose stack.
  - Verifies Docker Engine + Compose v2 are present (preflight); does **not**
    install Docker.
  - Renders `docker-compose.yml`, `Caddyfile` and `.env`; brings the stack up via
    `community.docker.docker_compose_v2`.
  - Optional separate admin console hostname (`keycloak_deploy_admin_hostname`,
    sets `KC_HOSTNAME_ADMIN` and a dedicated Caddy site + certificate).
  - Optional source-IP allowlist for the admin hostname
    (`keycloak_deploy_admin_hostname_allowed_ips`), enforced at the Caddy edge.
  - Defaults: Keycloak `26.6.2-2`, Caddy `2`, PostgreSQL `18`.
- **`keycloak_cfg` role** — configures a running Keycloak through its admin REST
  API (`community.general.keycloak_*` modules), declaratively and idempotently:
  - realms (`keycloak_cfg_realms`)
  - groups (`keycloak_cfg_groups`)
  - clients (`keycloak_cfg_clients`)
  - identity providers with inline mappers (`keycloak_cfg_identity_providers`)
  - realm signing/encryption keys (`keycloak_cfg_realm_keys`)
  - declarative user profiles (`keycloak_cfg_user_profiles`)
  - A single admin login (`master` realm) manages many realms.
- **Collection scaffolding** — `galaxy.yml`, `meta/runtime.yml`
  (`requires_ansible >= 2.15`), collection dependencies (`community.docker >= 3.0.0`,
  `community.general >= 9.4.0`).
- **Example playbooks** — `playbooks/deploy.yml`, `playbooks/configure.yml`.
- **`playbooks/export_realm.yml`** — auxiliary playbook that dumps a live realm's
  configuration into `keycloak_cfg_*` variables to bootstrap `keycloak_cfg`
  (produces a review-required scaffold; secrets are not exported).

### Notes

- All role variables are namespaced by role: `keycloak_deploy_*` and
  `keycloak_cfg_*`.
- `keycloak_cfg` is a thin pass-through: each list item is handed verbatim to the
  matching `community.general.keycloak_*` module, so it uses the modules' native
  parameter names (e.g. `parent_id` for realm keys and user profiles).
- `community.general >= 9.4.0` is required for the `keycloak_userprofile` module.

[Unreleased]: https://github.com/pescobar/ansible-collection-keycloak/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/pescobar/ansible-collection-keycloak/releases/tag/v1.0.0
