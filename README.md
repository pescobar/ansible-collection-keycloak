# pescobar.keycloak

An Ansible collection to **deploy** and **configure** [Keycloak](https://www.keycloak.org/).

It ships two roles:

| Role | Purpose |
| --- | --- |
| [`keycloak_deploy`](roles/keycloak_deploy/README.md) | Stand up Keycloak (production mode) behind a [Caddy](https://caddyserver.com/) TLS-terminating reverse proxy (automatic HTTPS via Let's Encrypt) with a PostgreSQL backend, as a Docker Compose stack. Does **not** install Docker. |
| [`keycloak_cfg`](roles/keycloak_cfg/README.md) | Configure a running Keycloak instance declaratively through its admin REST API: realms, groups, clients, identity providers, realm keys, required actions, authentication flows and user profiles. One admin login can manage many realms. |

```
   keycloak_deploy                              keycloak_cfg
   ──────────────                               ────────────
   Caddy (TLS) ─▶ Keycloak ─▶ PostgreSQL   +    realms / clients / IdPs / ...
                                                via the admin REST API
```

## Requirements

- **Controller:** ansible-core ≥ 2.16 (e.g. the `ansible` 10.x package) and:
  - `community.docker` and `ansible.utils`, installed automatically with the
    collection.
  - **`middleware_automation.keycloak` ≥ 3.1.3**, needed by `keycloak_cfg` and
    **not installed automatically** — install it yourself (see below). It holds
    the Keycloak modules that used to live in `community.general` (moved there in
    community.general 14), so this collection does not need `community.general`
    at all and leaves the version you have untouched. If it is missing,
    Ansible stops with `couldn't resolve module/action
    'middleware_automation.keycloak.keycloak_realm'`.
- **Deploy target:** Docker Engine + the Compose v2 plugin already installed and
  running (this collection does not install Docker).
- **DNS & firewall:** for Let's Encrypt, the Keycloak hostname must resolve
  publicly to the host with ports 80 and 443 reachable.

## Installation

From a built tarball or a git source:

```bash
ansible-galaxy collection install pescobar.keycloak
# required by keycloak_cfg, not pulled in automatically:
ansible-galaxy collection install 'middleware_automation.keycloak:>=3.1.3'
# or install every controller-side dependency at once:
ansible-galaxy collection install -r requirements.yml
```

## Quick start

```yaml
- name: Deploy and configure Keycloak
  hosts: keycloak
  become: true
  roles:
    - role: pescobar.keycloak.keycloak_deploy
      vars:
        keycloak_deploy_hostname: "auth.example.com"
        keycloak_deploy_acme_email: "admin@example.com"
        keycloak_deploy_admin_password: "{{ vault_keycloak_admin_password }}"
        keycloak_deploy_db_password: "{{ vault_keycloak_db_password }}"

    - role: pescobar.keycloak.keycloak_cfg
      vars:
        keycloak_cfg_url: "https://auth.example.com"
        keycloak_cfg_admin_password: "{{ vault_keycloak_admin_password }}"
        keycloak_cfg_realms:
          - realm: myapp
            enabled: true
            state: present
        keycloak_cfg_clients:
          - realm: myapp
            client_id: myapp-frontend
            public_client: true
            redirect_uris: ["https://app.example.com/*"]
            state: present
```

When both roles run in the same play with shared variables, `keycloak_cfg`
defaults its URL and admin credentials from the `keycloak_deploy_*` variables,
so you can omit them.

See [`playbooks/`](playbooks/) for runnable examples and each role's README for
the full variable reference.

## Seeding config from an existing realm

Already have a running Keycloak? You can generate the `keycloak_cfg_*` variables
from an existing realm instead of writing them by hand — either from a native
`kc.sh export` (preferred) or over the REST API. See
[**Seed the variables from it**](roles/keycloak_cfg/README.md#already-have-a-running-keycloak-seed-the-variables-from-it)
in the `keycloak_cfg` role README.

## Naming convention

All variables are namespaced by role: `keycloak_deploy_*` for the deploy role,
`keycloak_cfg_*` for the configure role.

## Changelog

See [`CHANGELOG.md`](CHANGELOG.md). This collection follows
[Semantic Versioning](https://semver.org/); the current version is declared in
[`galaxy.yml`](galaxy.yml).

## License

MIT
