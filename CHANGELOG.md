# Changelog

All notable changes to the `pescobar.keycloak` collection are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this collection adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Breaking:** `keycloak_cfg` now calls the Keycloak modules from
  **`middleware_automation.keycloak` (>= 3.1.3)** instead of `community.general`.
  The modules moved there in community.general 14 (which keeps only deprecated
  redirects, removed in 16), so on current Ansible the role failed with
  `couldn't resolve module/action 'community.general.keycloak_realm'`; and the
  `community.general` versions that still ship them are buggy on Keycloak 25+
  (authentication-flow priority reset before 10.2.0, no generated realm keys
  before 13.0.0). Option names are unchanged. The collection is **not installed
  automatically** — install it yourself (`ansible-galaxy collection install
  'middleware_automation.keycloak:>=3.1.3'` or `-r requirements.yml`).
  `community.general` is no longer a dependency, and the collection now needs
  ansible-core >= 2.16.
- `playbooks/export_realm.yml`: `kc_include_default_clients` /
  `kc_default_clients` replaced by a single `kc_skip_clients` list (defaults to
  the built-in clients; set `[]` to export every client).
- `keycloak_deploy`: the Docker preflight is a single `docker version` /
  `docker compose version` probe with one combined error message.

### Added

- `keycloak_cfg`: `keycloak_cfg_authentication_flows` manages authentication
  flows and their executions per realm via the `keycloak_authentication` module
  (e.g. set a default identity provider on the `browser` flow so users skip the
  Keycloak login page).

### Fixed

- `playbooks/export_realm.yml`: client secrets were written to the export in
  **cleartext** (Keycloak 26 returns them in the client representation) although
  the file header claimed they were masked; they are now dropped. User profiles
  are exported in the current `{realm, profile}` shape instead of the pre-1.0.0
  `{parent_id, config}` one.
- `keycloak_cfg`: the user profile was re-PUT (reported `changed`) on every run
  unless each attribute declared `multivalued`; the comparison now applies
  Keycloak's `multivalued: false` default.
- `keycloak_deploy`: Caddy forwarded `Host` / `X-Forwarded-Host` via `{host}`,
  which drops the port, so with `keycloak_deploy_https_port` other than 443
  Keycloak built absolute URLs (e.g. `Location` headers) without it. Caddy's
  default forwarding is used instead.
- Docs: `unmanagedAttributePolicy: DISABLED` (rejected by Keycloak) removed from
  the user-profile examples; the role README and `playbooks/configure.yml` showed
  the pre-1.0.0 user-profile shape; `kc.sh export` on a running stack needs
  `--http-management-port=9001`.

## [1.1.0] - 2026-11-25

### Added

- `keycloak_cfg`: `keycloak_cfg_required_actions` manages Authentication →
  Required actions per realm via
  `community.general.keycloak_authentication_required_actions` (e.g. turn off
  `CONFIGURE_TOTP` / `UPDATE_PASSWORD` when an external IdP owns them).

## [1.0.0] - 2026-07-23

First release as an Ansible collection. Converts the former standalone role into
`pescobar.keycloak` with two roles.

The *Changed* and *Fixed* entries, and the first two *Added* entries, landed
late but before the `1.0.0` tag, so they ship in the 1.0.0 artifact. Where they
conflict with the later *Added* or *Notes* entries (user-profile item shape,
`community.general` floor), they take precedence.

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

### Fixed

- `keycloak_cfg`: give every `loop` its own `loop_var` (`_kc_item`) to silence the
  "loop variable 'item' is already in use" warning when the role is invoked from a
  looping context.
- `gen_vars_from_export.py`: emit multiline PEM certificates/keys as YAML literal
  block scalars (`|`), and emit user profiles as raw `{realm, profile}` JSON that
  the role PUTs verbatim to `/users/profile`.

### Added

- `keycloak_cfg`: render a before/after `--diff` of pending user-profile changes
  via `ansible.utils.fact_diff` (the `uri` PUT that applies them cannot emit a
  diff). Adds an `ansible.utils >= 2.0.0` dependency (bundled with the ansible
  community package).
- `keycloak_cfg`: `files/gen_vars_from_export.py` — an offline converter that
  turns a native `kc.sh export` realm JSON into flat `keycloak_cfg_*` variables
  with module-native option names and named Vault placeholders for all secrets
  (including realm-key private material, which the REST API never returns). The
  REST-based `playbooks/export_realm.yml` remains as a no-host-access fallback.
  A `--with-secrets` flag inlines real secret values instead of placeholders;
  in that mode the tool warns on stderr and the output header flags the plaintext
  secrets, listing each by the Vault variable name it should be moved to.
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

[Unreleased]: https://github.com/pescobar/ansible-collection-keycloak/compare/1.1.0...HEAD
[1.1.0]: https://github.com/pescobar/ansible-collection-keycloak/releases/tag/1.1.0
[1.0.0]: https://github.com/pescobar/ansible-collection-keycloak/releases/tag/1.0.0
