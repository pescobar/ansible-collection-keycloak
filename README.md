# pescobar.keycloak

An Ansible collection to **deploy** and **configure** [Keycloak](https://www.keycloak.org/).

It ships two roles:

| Role | Purpose |
| --- | --- |
| [`keycloak_deploy`](roles/keycloak_deploy/README.md) | Stand up Keycloak (production mode) behind a [Caddy](https://caddyserver.com/) TLS-terminating reverse proxy (automatic HTTPS via Let's Encrypt) with a PostgreSQL backend, as a Docker Compose stack. Does **not** install Docker. |
| [`keycloak_cfg`](roles/keycloak_cfg/README.md) | Configure a running Keycloak instance declaratively (realms, groups, clients) through its admin REST API. One admin login can manage many realms. |

```
   keycloak_deploy                              keycloak_cfg
   ──────────────                               ────────────
   Caddy (TLS) ─▶ Keycloak ─▶ PostgreSQL   +    realms / groups / clients
                                                via the admin REST API
```

## Requirements

- **Controller:** Ansible ≥ 2.15 and the collection dependencies
  (`community.docker`, `community.general`), installed automatically with the
  collection or via `requirements.yml`.
- **Deploy target:** Docker Engine + the Compose v2 plugin already installed and
  running (this collection does not install Docker).
- **DNS & firewall:** for Let's Encrypt, the Keycloak hostname must resolve
  publicly to the host with ports 80 and 443 reachable.

## Installation

From a built tarball or a git source:

```bash
ansible-galaxy collection install pescobar.keycloak
# or, for the controller-side module dependencies:
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

## Exporting an existing realm

[`playbooks/export_realm.yml`](playbooks/export_realm.yml) dumps the live
configuration of an existing realm (realm settings, clients, groups, identity
providers + mappers, realm keys, user profile) into a YAML file laid out with
the `keycloak_cfg_*` variables, to bootstrap `keycloak_cfg`:

```bash
ansible-playbook pescobar/keycloak/playbooks/export_realm.yml \
  -e kc_url=https://auth.example.com -e kc_realm=myapp \
  -e kc_admin_password=... -e kc_export_dest=./myapp-keycloak_cfg.yml
```

The output is a **scaffold to review**, not a guaranteed drop-in: secrets are not
recoverable (client secrets are masked, key private material is never returned),
and values use Keycloak's REST representation (camelCase, plus server-managed
fields) which you rename/prune to match the `keycloak_*` module options. See the
playbook header for details.

## Naming convention

All variables are namespaced by role: `keycloak_deploy_*` for the deploy role,
`keycloak_cfg_*` for the configure role.

## License

MIT
